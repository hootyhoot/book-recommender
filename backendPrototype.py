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

load_dotenv() #loading api keys

#downloading stopwords files
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)
nltk.download('wordnet', quiet=True)

#loading embeddings csv
df = pd.read_csv('embeddings.csv')
df['embeddings'] = df['embeddings'].apply(eval)
tfidf_matrix = df['embeddings'].tolist()

#declaring lemmatiser and setting stopwords to use english stopwords
lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

#function to preprocess the user queries for embeddings
def preprocess_text(text):
    text = re.sub(r'http\S+', '', text) #removing urls
    text = re.sub(r'[^a-zA-Z\s]', '', text) #removing symbols
    text = text.lower() #converting to lowercase
    tokens = word_tokenize(text) #tokenising the string (splitting into smaller chunks)
    tokens = [word for word in tokens if word not in stop_words] #from those tokens remove stopwords (e.g a, the, is, are, etc) which are used a lot but carry very little information for the embedder 
    tokens = [lemmatizer.lemmatize(word) for word in tokens] #from those tokens convert the words into their base forms (changed and changes becomes change)
    return ' '.join(tokens) #combine all the tokens back into a string to send off to embedder which only takes strings

#function to send and receive a request to OpenAI for embedding the user query
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

#function for recommending based on user description
def get_recommendations_by_description(user_query):
    cleaned_query = preprocess_text(user_query) #preprocess the description
    query_embedding = get_openai_embedding(cleaned_query) #get the embedding of that description
    similarity_scores = cosine_similarity([query_embedding], tfidf_matrix) #array that contains the result of the cosine distance of the OpenAI embedding to all embeddings in the database
    top_n = 15 #number of similar books to return
    top_n_indices = similarity_scores[0].argsort()[-top_n:][::-1] #from the similarity_scores array, sort it by highest score and give only the first top_n results
    recommended_books = df.iloc[top_n_indices]
    return recommended_books[['Book', 'Author', 'Avg_Rating', 'URL']]

#function for recommending based on an existing book title
##------TODO ^^ If title not in csv, call ISBNdb, vectorise desc, append vector to embedding csv----##
def get_recommendations_by_title(book_title):
    book_titles = df['Book'].tolist() #separating all the book titles from database into separate dataframe
    matches = process.extract(book_title, book_titles, limit=5) #using fuzzy search, find the user input book title from all the books in the database, return the closest 5 books
    
    if matches[0][1] >= 90:  #if a book title has a higher than 90% confidence that it is a book in the database then
        matched_book = df[df['Book'] == matches[0][0]].iloc[0] #extract the matched book from the database
        book_embedding = matched_book['embeddings'] #and take the embedding of that matched book
        
        #using the book found's embedding, calculate the cosine distance of it to all the books in the database
        similarity_scores = cosine_similarity([book_embedding], tfidf_matrix)
        
        top_n = 15 #same as above return the top 15 books with the closest cosine distance
        top_n_indices = similarity_scores[0].argsort()[-top_n:][::-1]
        
        #remove the book title that the user entered from the list of similar books (of course the most similar book in the database is the book itself)
        recommended_books = df.iloc[top_n_indices]
        recommended_books = recommended_books[recommended_books['Book'] != matched_book['Book']]
        
        return recommended_books[['Book', 'Author', 'Avg_Rating', 'URL']]
    else:
        #else return a list of book titles that are semantically similar to the book title
        return pd.DataFrame([{'Book': match[0], 'similarity': match[1]} for match in matches])

def display_menu():
    print("\nBook Recommendation System")
    print("1. Recommend by description")
    print("2. Recommend by title")
    print("3. Exit")

def main():
    while True:
        display_menu()
        choice = input("Enter your choice (1-3): ")

        if choice == '1':
            query = input("Enter a description of the book you're looking for: ")
            recommendations = get_recommendations_by_description(query)
            print("\nRecommendations based on your description:")
            print(recommendations.to_string(index=False))
        elif choice == '2':
            query = input("Enter the title of a book you like: ")
            recommendations = get_recommendations_by_title(query)
            print("\nRecommendations based on the book title:")
            print(recommendations.to_string(index=False))
        elif choice == '3':
            print("Thank you for using the Book Recommendation System. Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()