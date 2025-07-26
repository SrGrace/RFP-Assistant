from datetime import datetime
import os

from sentence_transformers import SentenceTransformer, util
from langchain_ibm import ChatWatsonx
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenTextParams
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from markdown_pdf import MarkdownPdf, Section
import fitz  # PyMuPDF
from docx import Document

from scrapers.alberta import fetch_alberta_opportunities
from scrapers.ariba import fetch_ariba_opportunities

from models import RfpOpportunity

os.environ["TOKENIZERS_PARALLELISM"] = ("false")  ## to ensure hugging face model don't get into deadlock

# Init models and LLM
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

from dotenv import load_dotenv
load_dotenv(override=True)

wx_credentials = {
    "url": os.getenv("IBM_CLOUD_URL"),
    "apikey": os.getenv("API_KEY"),
    "project_id": os.getenv("PROJECT_ID"),
}
llm = ChatWatsonx(
    model_id="meta-llama/llama-4-maverick-17b-128e-instruct-fp8",
    params={GenTextParams.MAX_NEW_TOKENS: 4096, GenTextParams.DECODING_METHOD: "sample", GenTextParams.TEMPERATURE: 0.7},
    **wx_credentials,
)

prompt_template = PromptTemplate(
    template="""You are an expert proposal writer. Based on the information below, generate a professional RFP response document with the following four sections:

## 1. Executive Summary
Provide a high-level overview of the proposal. Summarize the client's needs, the proposed solution, and the value offered.

## 2. Cover Letter
Write a formal letter addressed to the client. Thank them for the opportunity, briefly highlight your capabilities, express interest in collaboration, and sign with just the company signature.

## 3. Capabilities Mapping
Map the company's strengths, services, and experience to the client's specific opportunity requirements. Use bullet points or concise paragraphs.

## 4. Relevant Past Projects
Describe 2-3 relevant past projects. Include the client, problem statement, approach taken, and the outcome or impact. Highlight alignment with the current opportunity.

---

### Opportunity Details
- **Title**: {title}
- **Client**: {customer}
- **Description**: {description}

---

### Company Profile
- **Name**: {company_name}
- **Overview**: {company_description}

---

### Additional RFP Context (from uploaded file)
{rfp_context}

---

Respond in a clear, formal, and persuasive tone. Use markdown-style headers (##) to separate each section
""",
    input_variables=["title", "customer", "description", "company_name", "company_description", "rfp_context"]
)

llm_chain = prompt_template | llm | StrOutputParser()


def embed_text(text: str):
    return embedding_model.encode(text, convert_to_tensor=True)

def calculate_match_score(company_embed, text_embed) -> float:
    sim = util.pytorch_cos_sim(company_embed, text_embed)
    return float(sim.item())

################################  Starting Nodes  ################################

def fetch_and_rank_opportunities(state):
    profile = state["company_profile"]
    company_embed = embed_text("Description: {}".format(profile.description))

    scrapers = [fetch_alberta_opportunities, fetch_ariba_opportunities]
    
    all_opps = []
    for scraper in scrapers:
        try:
            all_opps.extend(scraper(RfpOpportunity))
        except Exception as e:
            print(f"{scraper} failed: {e}")
            continue

    for opp in all_opps:
        text = f"{opp.title} {opp.description}"
        opp.match_score = calculate_match_score(company_embed, embed_text(text))

    all_opps.sort(key=lambda x: x.match_score, reverse=True)

    # return {"all_opportunities": all_opps[:10]}
    state["all_opportunities"] = all_opps[:10]
    return state

from langgraph.graph import END

def wait_for_opportunity_selection(state):
    # Pause execution and wait for user input
    return END

def extract_text_from_file(file):
    if not file:
        # No file uploaded, return empty string
        return 
    
    content = ""
    if file.filename.endswith(".pdf"):
        with fitz.open(stream=file.file.read(), filetype="pdf") as doc:
            for page in doc:
                content += page.get_text()
    elif file.filename.endswith(".docx"):
        doc = Document(file.file)
        content = "\n".join([p.text for p in doc.paragraphs])
    return content[:2000]  # cap to 2000 chars for context

def extract_rfp_context(state):
    if "rfp_file" not in state:
        state["rfp_file_context"] = ""
        return state

    file = state["rfp_file"]
    state["rfp_file_context"] = extract_text_from_file(file)
    return state

def generate_rfp_response(state):
    if "selected_opportunity" not in state:
        raise ValueError("No selected_opportunity in state")
    
    opportunity = state["selected_opportunity"]
    company = state["company_profile"]
    rfp_context = state.get("rfp_file_context", "")
    result = llm_chain.invoke({
        "title": opportunity.title,
        "customer": opportunity.customer,
        "description": opportunity.description,
        "company_name": company.name,
        "company_description": company.description,
        "rfp_context": rfp_context,
    })
    return {"rfp_response_markdown": result}

def save_pdf(state):
    result = state["rfp_response_markdown"]
    title = state["selected_opportunity"].title
    company_name = state["company_profile"].name
    ref = state["selected_opportunity"].ref_number

    header = f"""<div style="text-align:center">

# Proposal for {title}

**Submitted by**: {company_name}  
**Date**: {datetime.today().strftime('%B %d, %Y')}  
**RFP Reference #**: {ref}  

</div>

---
"""
    output_file = f"generated_pdfs/rfp_response_{title}.pdf"
    pdf = MarkdownPdf(toc_level=1)
    pdf.add_section(Section(header + "\n\n" + result))
    pdf.save(output_file)
    return {"rfp_pdf_path": output_file}
