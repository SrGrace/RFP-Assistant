import streamlit as st
import pandas as pd
import requests
from datetime import datetime

API_BASE = "http://localhost:6001"  # Your backend URL

# Set page configuration
st.set_page_config(page_title="RFP Assistant", layout="wide")

# Helper function to format dates
def format_date(date_str):
    try:
        # return datetime.strptime(date_str, "%Y/%m/%d").date
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")
    except:
        return date_str

# Initialize session state
if "opportunities" not in st.session_state:
    st.session_state["opportunities"] = []
if "selected_opportunity_index" not in st.session_state:
    st.session_state["selected_opportunity_index"] = None
if "company_name" not in st.session_state:
    st.session_state["company_name"] = ""
if "company_description" not in st.session_state:
    st.session_state["company_description"] = ""

# Title
st.title("🇨🇦 RFP Assistant")

# Step 1: Company Profile Input
st.header("1. Company Profile")
with st.form("company_profile_form"):
    company_name = st.text_input("Company Name", value=st.session_state["company_name"], placeholder="Enter your company name")
    company_description = st.text_area("Company Description", value=st.session_state["company_description"], placeholder="Describe your company's capabilities")
    submitted = st.form_submit_button("Search Opportunities")
    if submitted:
        if not company_name or not company_description:
            st.error("Please provide both company name and description.")
        else:
            st.session_state["company_name"] = company_name
            st.session_state["company_description"] = company_description
            # API call to fetch opportunities
            try:
                with st.spinner("Fetching opportunities..."):
                    response = requests.post(f"{API_BASE}/search-opportunities", 
                        json={
                            "name": company_name,
                            "description": company_description
                        }
                    )
                if response.status_code == 200:
                    st.session_state["opportunities"] = response.json()
                    st.success("Opportunities fetched successfully!")
                else:
                    st.error("Failed to fetch opportunities.")
            except Exception as e:
                st.error(f"Error: {e}")

# Step 2: Opportunity Selection
if st.session_state["opportunities"]:
    st.header("2. Select an Opportunity")
    # Prepare data for display
    df = pd.DataFrame(st.session_state["opportunities"])
    df["Posting Date"] = df["posting_date"].apply(format_date)
    df["Closing Date"] = df["closing_date"].apply(format_date)
    df["Region"] = df["region_of_delivery"].apply(lambda x: ", ".join(x))
    df["Posting URL"] = df["posting_url"]
    df_display = df[["title", "customer", "Region", "Posting Date", "Closing Date", "Posting URL"]]
    df_display.columns = ["Title", "Customer", "Region", "Posting Date", "Closing Date", "Posting URL"]

    # Search functionality
    search_term = st.text_input("Search Opportunities", placeholder="Search by title or customer")
    if search_term:
        df_display = df_display[df_display["Title"].str.contains(search_term, case=False) | df_display["Customer"].str.contains(search_term, case=False)]

    # Display table with radio buttons for selection
    st.dataframe(df_display)
    selected_index = st.radio("Select an opportunity to proceed", df_display.index, format_func=lambda x: df_display.loc[x, "Title"])
    st.session_state["selected_opportunity_index"] = selected_index

# Step 3: RFP Response Generation
if st.session_state["selected_opportunity_index"] is not None:
    st.header("3. Generate RFP Response")
    opp = st.session_state["opportunities"][st.session_state["selected_opportunity_index"]]

    with st.form("rfp_response_form"):
        rfp_title = st.text_input("RFP Title", value=opp["title"])
        rfp_description = st.text_area("RFP Description", value=opp["description"])
        customer = st.text_input("Customer", value=opp["customer"])
        ref_number = st.text_input("Reference Number", value=opp["ref_number"])
        uploaded_file = st.file_uploader("Upload Additional Documents (PDF/DOCX)", type=["pdf", "docx"])
        generate = st.form_submit_button("Generate Response")

        if generate:
            if not rfp_title or not rfp_description or not customer:
                st.error("Please fill in all required fields.")
            else:
                data = {
                    "title": rfp_title,
                    "description": rfp_description,
                    "customer": customer,
                    "ref_number": ref_number,
                    "company_name": st.session_state["company_name"],
                    "company_description": st.session_state["company_description"]
                }
                files = {"rfp_file": uploaded_file.getvalue()} if uploaded_file else None

                try:
                    with st.spinner("Generating RFP response..."):
                        response = requests.post(f"{API_BASE}/generate-rfp-response", data=data, files=files)
                    if response.status_code == 200:
                        st.success("RFP response generated successfully!")
                        st.session_state["rfp_response_pdf"] = response.json().get("file_url")
                    else:
                        st.error("Failed to generate RFP response.")
                except Exception as e:
                    st.error(f"Error: {e}")

# Show download button outside the form
# if "rfp_response_pdf" in st.session_state:
#     st.download_button("📄 Download RFP Response PDF", st.session_state["rfp_response_pdf"], file_name="rfp_response.pdf")

if "rfp_response_pdf" in st.session_state:
    st.markdown(f"""
        ##### 📄 [Download RFP Response PDF]({st.session_state['rfp_response_pdf']})  
        *(Link expires in 7 days)*
    """, unsafe_allow_html=True)


# streamlit run rfp_assistant_frontend.py