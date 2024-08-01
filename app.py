from flask import Flask, render_template, request, jsonify
import pandas as pd
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

# Download necessary NLTK data files
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

# Load preprocessed data with embeddings
df = pd.read_parquet('embeddings.parquet')
df.info(verbose=False, memory_usage="deep")
tfidf_matrix = df['embeddings'].tolist()

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
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {os.getenv('openai_key')}",
    }
    data = {
        "input": text,
        "model": "text-embedding-3-small"
    }
    response = requests.post('https://api.openai.com/v1/embeddings', headers=headers, json=data)
    return response.json()['data'][0]['embedding']

def preprocess_query(query):
    return preprocess_text(query)

def get_recommendations_by_description(user_query):
    cleaned_query = preprocess_query(user_query)
    query_embedding = get_openai_embedding(cleaned_query)
    similarity_scores = cosine_similarity([query_embedding], tfidf_matrix)
    top_n = 15
    top_n_indices = similarity_scores[0].argsort()[-top_n:][::-1]
    recommended_books = df.iloc[top_n_indices]
    return recommended_books[['Book', 'Author', 'Avg_Rating', 'URL']].to_dict('records')

def get_recommendations_by_title(book_title):
    #fuzzy search for book title
    book_titles = df['Book'].tolist()
    matches = process.extract(book_title, book_titles, limit=5)

    if matches[0][1] >= 90:  #if we have a close match (90% similarity or higher)
        matched_book = df[df['Book'] == matches[0][0]].iloc[0]
        ##matched_books = df [df['Book'] == matches [0][0]].iloc[0] ##array of books that have a higher than 90% similarity (e.g for sequels of books that includes the same titles, harry potter for instance has like 6 books with harry potter in them but you dont want a rec for harry potter 6 times)
        book_embedding = matched_book['embeddings']

        #calc similarity scores
        similarity_scores = cosine_similarity([book_embedding], tfidf_matrix)

        top_n = 15
        top_n_indices = similarity_scores[0].argsort()[-top_n:][::-1]

        #if book found removed from recs (dont want to show a book that the user wants a similar book to)
        recommended_books = df.iloc[top_n_indices]
        recommended_books = recommended_books[recommended_books['Book'] != matched_book['Book']]

        return recommended_books[['Book', 'Author', 'Avg_Rating', 'URL']].to_dict('records')
    else:
        #return potential matches
        return [{'Book': match[0], 'similarity': match[1]} for match in matches]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/recommend', methods=['POST'])
def recommend():
    #query-form
    search_type = request.form['search_type'] #search_type select tag
    query = request.form['query'] #query input tag

    #called and returned in ajax
    if search_type == 'description':
        recommendations = get_recommendations_by_description(query)
    else:  # search_type == 'title'
        recommendations = get_recommendations_by_title(query)

    return jsonify(recommendations)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
