                 
# Book Recommender

A **WIP** web app to recommend **your** next book using embeddings and similarity search.
 
## Getting Started

After installing the required packages with
```bash
pip install -r requirements.txt
```
Run the app with
```bash
python app.py
```
You can then access the site on  http://127.0.0.1:5000

## Prerequisites

Create a .env file with your OpenAI API key under 'openai_key' then install the packages below

Apart from anaconda/miniconda's included packages all you need is 
- rapidfuzz
- fuzzywuzzy
- langdetect
- python-dotenv
- requests
