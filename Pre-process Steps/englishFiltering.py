
import pandas as pd
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

DetectorFactory.seed = 0
df = pd.read_csv('goodreads_data.csv') #loading csv

#function to detect if text argument is english or not 
def is_english(text):
    try:
        return detect(text) == 'en'
    except LangDetectException:
        return False

#combining all columns into a single string for easy passing to detection function
df['combined_text'] = df.apply(lambda row: f"{row['Book']} {row['Description']} {row['Genres']}", axis=1)

#passing all the combined text rows to the detection function and putting the english values into a new dataframe and saving it into a new file
df_english = df[df['combined_text'].apply(is_english)]
df_english.to_csv('filtered_goodreads_data.csv', index=False)