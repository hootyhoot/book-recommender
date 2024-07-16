                 
# Book Recommender

A **WIP** web app to recommend **your** next book using embeddings and similarity search.
 
## Getting Started

After installing the required packages generate the embeddings.csv file from the 'Pre-Process Steps' folder using
```bash
python embedding.py 
```
Then we can run
```bash
python app.py
```
You can then access the site on  http://127.0.0.1:5000
Depending on your storage speed, after it downloads the nltk stopwords it might take up to a minute or two to load the 220mb embeddings.csv file generated from the previous step

## Prerequisites

Create a .env file with your OpenAI API key under 'openai_key' then install the packages below

Apart from anaconda/miniconda's included packages all you need is 
- rapidfuzz
- fuzzywuzzy
- langdetect
- python-dotenv
- requests
