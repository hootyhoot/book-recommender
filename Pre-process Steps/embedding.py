import pandas as pd
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
import re
import aiohttp
import asyncio
from sklearn.metrics.pairwise import cosine_similarity
import os
from dotenv import load_dotenv

load_dotenv()

nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

df = pd.read_csv('filtered_goodreads_data.csv') 

lemmatizer = WordNetLemmatizer()
stop_words = set(stopwords.words('english'))

def preprocess_text(text):
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    text = text.lower()
    tokens = word_tokenize(text)
    tokens = [word for word in tokens if word not in stop_words]
    tokens = [lemmatizer.lemmatize(word) for word in tokens]
    return ' '.join(tokens)

def combine_fields(row):
    combined_text = f"{row['Book']} {row['Description']} {row['Genres']}"
    ##--TODO user query is processed through an LLM to generate a 'record' with form Book, Desc lemmatised and tokenised, Possible genres
    return combined_text

df['combined_text'] = df.apply(combine_fields, axis=1)
df['cleaned_combined_text'] = df['combined_text'].apply(preprocess_text)

#async function for batch embeddings
async def get_openai_embedding(session, text):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {os.getenv('openai_key')}",
    }
    data = {
        "input": text,
        "model": "text-embedding-3-small"
    }
    async with session.post('https://api.openai.com/v1/embeddings', headers=headers, json=data) as response:
        result = await response.json()
        if 'data' in result:
            return result['data'][0]['embedding']
        elif 'error' in result and result['error']['code'] == 'rate_limit_exceeded':
            print("Rate limit reached. Waiting for 60 seconds before retrying...")
            await asyncio.sleep(60)  #async await due to RPM rate limits
            return await get_openai_embedding(session, text)  #retry the same request
        else:
            print(f"Error while fetching embedding for text: {text[:30]}...")
            print(result)
            return None

async def get_all_embeddings():
    async with aiohttp.ClientSession() as session:
        tasks = []
        for text in df['cleaned_combined_text']:
            task = asyncio.ensure_future(get_openai_embedding(session, text))
            tasks.append(task)
        embeddings = await asyncio.gather(*tasks)
        df['embeddings'] = embeddings

asyncio.run(get_all_embeddings())

#drop rows where embeddings are None
df = df.dropna(subset=['embeddings'])

df.to_csv('embeddings.csv', index=False)