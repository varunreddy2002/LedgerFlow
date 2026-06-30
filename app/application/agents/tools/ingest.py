from langchain.tools import tool
import pandas as pd

@tool
def inspect_csv(file):
    """
    Tool for inspecting the csv file
    Description: It takes file as pdf and inspect the data and the columns of it.
    Input - File Path
    Output - columns and first few rows of data
    """
    df = pd.read_csv(file)
    peek_data = df.head(3)
    cols = df.columns

    return peek_data,cols