import pandas as pd
import numpy as np
import ast

req_cols = ['Book', 'Author', 'Avg_Rating', 'URL', 'embeddings']
df = pd.read_csv('embeddings.csv', usecols=req_cols)
df.info(verbose=False, memory_usage="deep")
print(df['embeddings'].memory_usage(index=False, deep=True))
print(df.dtypes)

df['embeddings'] = df['embeddings'].apply(lambda x: np.array(ast.literal_eval(x), dtype=np.float32))

df.to_parquet('embeddings.parquet', compression='gzip')

df = pd.read_parquet('embeddings.parquet')
df.info(verbose=False, memory_usage="deep")
print(df['embeddings'].memory_usage(index=False, deep=True))
print(df.dtypes)

