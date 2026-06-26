import streamlit as st
import pandas as pd
import pdfplumber
from google import genai
from pydantic import BaseModel
import json

# --- Page Settings ---
st.set_page_config(page_title="Statement to Tally Converter", layout="wide")
st.title("Bank Statement to Tally Converter v2.0")

# --- Security: Sidebar for API Key ---
st.sidebar.header("Setup Instructions")
st.sidebar.write("1. Get your free API key from [Google AI Studio](https://aistudio.google.com/).")
api_key = st.sidebar.text_input("2. Paste your API Key here:", type="password")

# --- Define the AI Output Structure ---
class TallyEntry(BaseModel):
    extracted_party_name: str
    tally_voucher_type: str
    suggested_ledger: str

# --- Function to Extract Data ---
def extract_data(file):
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    elif file.name.endswith('.pdf'):
        data = []
        with pdfplumber.open(file) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    data.extend(table)
        if len(data) > 1:
            return pd.DataFrame(data[1:], columns=data[0])
        else:
            return None

# --- Main Application Logic ---
if not api_key:
    st.warning("Please enter your Gemini API key in the sidebar to start.")
else:
    client = genai.Client(api_key=api_key)
    
    uploaded_file = st.file_uploader("Upload your Bank Statement (CSV or PDF)", type=["csv", "pdf"])

    if uploaded_file is not None:
        st.info("File uploaded successfully. Extracting data...")
        
        try:
            df = extract_data(uploaded_file)
            
            if df is not None:
                st.write("Here is a preview of the raw data we found:")
                st.dataframe(df.head()) 
                
                # --- UPGRADED: Map Columns Section ---
                st.write("---")
                st.write("### Map Your Columns:")
                st.write("Tell the app where to find your data. If your statement doesn't have a Running Balance, just select 'Not Present'.")
                
                columns_list = df.columns.tolist()
                columns_list_with_none = ["Not Present"] + columns_list
                
                # Created a two-row layout for the 5 dropdowns
                col1, col2, col3 = st.columns(3)
                date_col = col1.selectbox("Date Column", columns_list)
                narration_col = col2.selectbox("Narration/Description", columns_list)
                balance_col = col3.selectbox("Running Balance/Closing Figure", columns_list_with_none)
                
                col4, col5 = st.columns(2)
                deposit_col = col4.selectbox("Deposits/Credits", columns_list)
                withdrawal_col = col5.selectbox("Withdrawals/Debits", columns_list)
                
                if st.button("Process with AI"):
                    st.write("Analyzing narrations and mapping to Tally ledgers. This might take a minute...")
                    
                    results = []
                    
                    # Loop through the rows and ask the AI
                    for index, row in df.iterrows():
                        narration_text = row[narration_col]
                        deposit_amt = row[deposit_col]
                        withdrawal_amt = row[withdrawal_col]
                        
                        prompt = f"""
                        Analyze this bank transaction:
                        Narration: {narration_text}
                        Deposit: {deposit_amt}
                        Withdrawal: {withdrawal_amt}
                        
                        1. Extract the core party name from the narration.
                        2. Determine the Tally Prime voucher type (Receipt F6, Payment F5, Contra F4).
                        3. Suggest a generic ledger account name based on standard accounting principles.
                        """
                        
                        try:
                            response = client.models.generate_content(
                                model='gemini-2.5-flash',
                                contents=prompt,
                                config={
                                    'response_mime_type': 'application/json',
                                    'response_schema': TallyEntry,
                                    'temperature': 0.1, 
                                },
                            )
                            
                            result_dict = json.loads(response.text)
                            
                            # --- UPGRADED: Adding Date and Balance to final output ---
                            results.append({
                                "Date": row[date_col], 
                                "Original Narration": narration_text,
                                "Withdrawal": withdrawal_amt,
                                "Deposit": deposit_amt,
                                "Running Balance": row[balance_col] if balance_col != "Not Present" else "",
                                "Extracted Party": result_dict['extracted_party_name'],
                                "Tally Voucher": result_dict['tally_voucher_type'],
                                "Tally Ledger": result_dict['suggested_ledger']
                            })
                            
                        except Exception as e:
                            pass # Skip rows that cause errors
                            
                    # Display the final clean table
                    st.success("Processing Complete!")
                    final_df = pd.DataFrame(results)
                    st.dataframe(final_df)
                    
                    # Create the Excel download button
                    output_filename = "Tally_Import_Ready.xlsx"
                    final_df.to_excel(output_filename, index=False)
                    
                    with open(output_filename, "rb") as file:
                        st.download_button(
                            label="Download Excel File for Tally",
                            data=file,
                            file_name=output_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
            else:
                st.error("Could not find a readable table in this file.")
                
        except Exception as e:
            st.error(f"An error occurred reading the file: {e}")