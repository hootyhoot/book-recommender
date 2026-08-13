from flask import Flask, render_template, request, jsonify, url_for, send_from_directory
import pandas as pd
import numpy as np
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
import re
import requests
from sklearn.metrics.pairwise import cosine_similarity
from fuzzywuzzy import process
import os
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()

# NLTK data is pre-downloaded once at build time (see the build command:
# `python -m nltk.downloader -d ./nltk_data ...`) into a folder next to this
# file, so containers never need network access for it on cold start.
# Adding it to nltk's search path explicitly avoids depending on cwd or an
# env var being set correctly by the host.
_nltk_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nltk_data')
if os.path.isdir(_nltk_data_dir):
    nltk.data.path.append(_nltk_data_dir)

# Local-dev fallback for when that data isn't already present (e.g. running
# app.py directly without having run the build command first).
for _resource, _path in [('punkt', 'tokenizers/punkt'), ('stopwords', 'corpora/stopwords'), ('wordnet', 'corpora/wordnet')]:
    try:
        nltk.data.find(_path)
    except LookupError:
        nltk.download(_resource)

# Load preprocessed data with embeddings.
# The embeddings column comes out of parquet as a column of per-row numpy
# arrays; a plain `.tolist()` blows that up into ~9700 * 1536 individual
# Python float objects (~400MB) on top of the DataFrame's own copy. Pull it
# into one compact float32 matrix instead and drop it from the DataFrame,
# which is the difference between comfortably fitting in 512MB and not.
df = pd.read_parquet('embeddings.parquet')
tfidf_matrix = np.array(df['embeddings'].tolist(), dtype=np.float32)
df = df.drop(columns=['embeddings']).reset_index(drop=True)
df.info(verbose=False, memory_usage="deep")

# Initialize lemmatizer
lemmatizer = WordNetLemmatizer()

# Define stop words
stop_words = set(stopwords.words('english'))

def preprocess_text(text):
    # Remove URLs
    text = re.sub(r'http\S+', '', text)
    # Remove non-alphabetic characters
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    # Convert to lowercase
    text = text.lower()
    # Tokenize
    tokens = word_tokenize(text)
    # Remove stopwords
    tokens = [word for word in tokens if word not in stop_words]
    # Lemmatize
    tokens = [lemmatizer.lemmatize(word) for word in tokens]
    return ' '.join(tokens)

def get_openai_embedding(text):
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {os.getenv('openai_key')}",
        }
        data = {
            "input": text,
            "model": "text-embedding-3-small"
        }
        response = requests.post('https://api.openai.com/v1/embeddings', headers=headers, json=data, timeout=30)
        response.raise_for_status()  # Raises HTTPError for bad responses
        
        result = response.json()
        
        # Check if the response has the expected structure
        if 'data' not in result or len(result['data']) == 0:
            raise ValueError("OpenAI API returned unexpected response format")
        
        return result['data'][0]['embedding']
    
    except requests.exceptions.Timeout:
        raise Exception("OpenAI API request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        raise Exception("Failed to connect to OpenAI API. Please check your internet connection.")
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            raise Exception("Invalid OpenAI API key. Please check your credentials.")
        elif response.status_code == 429:
            raise Exception("OpenAI API rate limit exceeded. Please try again later.")
        elif response.status_code == 500:
            raise Exception("OpenAI API is experiencing issues. Please try again later.")
        else:
            raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")
    except KeyError:
        raise Exception("Unexpected response format from OpenAI API")
    except Exception as e:
        raise Exception(f"Error getting embedding: {str(e)}")

def preprocess_query(query):
    return preprocess_text(query)

def get_recommendations_by_description(user_query):
    try:
        if not user_query or user_query.strip() == "":
            raise ValueError("Please enter a description to search")
        
        cleaned_query = preprocess_query(user_query)
        
        if not cleaned_query or cleaned_query.strip() == "":
            raise ValueError("Your query didn't contain any meaningful words. Please try a different description.")
        
        query_embedding = get_openai_embedding(cleaned_query)
        similarity_scores = cosine_similarity([query_embedding], tfidf_matrix)
        top_n = 15
        top_n_indices = similarity_scores[0].argsort()[-top_n:][::-1]
        recommended_books = df.iloc[top_n_indices]
        return recommended_books[['Book', 'Author', 'Avg_Rating', 'URL']].to_dict('records')
    
    except ValueError as e:
        raise Exception(str(e))
    except Exception as e:
        raise Exception(f"Error processing description search: {str(e)}")

def get_recommendations_by_title(book_title):
    try:
        if not book_title or book_title.strip() == "":
            raise ValueError("Please enter a book title to search")
        
        # Fuzzy search for book title
        book_titles = df['Book'].tolist()
        matches = process.extract(book_title, book_titles, limit=5)

        if matches[0][1] >= 92:  # If we have a close match (92% similarity or higher)
            matched_position = np.where((df['Book'] == matches[0][0]).values)[0][0]
            matched_book = df.iloc[matched_position]
            book_embedding = tfidf_matrix[matched_position]

            # Calculate similarity scores
            similarity_scores = cosine_similarity([book_embedding], tfidf_matrix)

            top_n = 15
            top_n_indices = similarity_scores[0].argsort()[-top_n:][::-1]

            # Remove the matched book from recommendations
            recommended_books = df.iloc[top_n_indices]
            recommended_books = recommended_books[recommended_books['Book'] != matched_book['Book']]

            return recommended_books[['Book', 'Author', 'Avg_Rating', 'URL']].to_dict('records')
        else:
            # Return potential matches with Author
            potential_matches = []
            for match in matches:
                book_info = df[df['Book'] == match[0]].iloc[0]
                potential_matches.append({
                    'Book': match[0],
                    'similarity': match[1],
                    'Author': book_info['Author']
                })
            return potential_matches
    
    except ValueError as e:
        raise Exception(str(e))
    except Exception as e:
        raise Exception(f"Error processing title search: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(app.static_folder, 'favicon.ico')

@app.route('/apple-touch-icon.png')
def apple_touch_icon():
    return send_from_directory(app.static_folder, 'apple-touch-icon.png')

@app.route('/apple-touch-icon-precomposed.png')
def apple_touch_icon_precomposed():
    return send_from_directory(app.static_folder, 'apple-touch-icon-precomposed.png')

@app.route('/recommend', methods=['POST'])
def recommend():
    try:
        # Get form data
        search_type = request.form.get('search_type')
        query = request.form.get('query')
        
        # Validate inputs
        if not search_type:
            return jsonify({'error': 'Please select a search type'}), 400
        
        if not query:
            return jsonify({'error': 'Please enter a search query'}), 400
        
        # Process based on search type
        if search_type == 'description':
            recommendations = get_recommendations_by_description(query)
        elif search_type == 'title':
            recommendations = get_recommendations_by_title(query)
        else:
            return jsonify({'error': 'Invalid search type'}), 400

        return jsonify(recommendations)
    
    except Exception as e:
        # Log the error for debugging
        app.logger.error(f"Error in /recommend: {str(e)}")
        
        # Return user-friendly error message
        error_message = str(e)
        if not error_message or error_message == "":
            error_message = "An unexpected error occurred. Please try again."
        
        return jsonify({'error': error_message}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
