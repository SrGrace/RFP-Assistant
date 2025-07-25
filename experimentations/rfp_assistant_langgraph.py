from typing import Optional, List
from fastapi import FastAPI, UploadFile, Form, File, HTTPException
from fastapi.responses import FileResponse
from langgraph.graph import StateGraph, END
from nodes import (
    fetch_and_rank_opportunities,
    wait_for_opportunity_selection,
    extract_rfp_context,
    generate_rfp_response,
    save_pdf,
)
from models import CompanyProfile, RfpOpportunity
from state_store import create_state, get_state, update_state

app = FastAPI(title="Canadian RFP Assistant")

from typing import TypedDict

class RfpFlowState(TypedDict, total=False):
    company_profile: CompanyProfile
    all_opportunities: List[RfpOpportunity]
    selected_opportunity: RfpOpportunity
    rfp_file: Optional[UploadFile]
    rfp_file_context: Optional[str]
    rfp_response_markdown: Optional[str]
    rfp_pdf_path: Optional[str]

# Setup LangGraph workflow
workflow = StateGraph(state_schema=RfpFlowState)
workflow.add_node("fetch_opportunities", fetch_and_rank_opportunities)
workflow.add_node("wait_for_selection", wait_for_opportunity_selection)
workflow.add_node("extract_context", extract_rfp_context)
workflow.add_node("generate_response", generate_rfp_response)
workflow.add_node("save_pdf", save_pdf)

workflow.set_entry_point("fetch_opportunities")
workflow.add_edge("fetch_opportunities", "wait_for_selection")
workflow.add_conditional_edges(
    "wait_for_selection",
    lambda state: "extract_context" if "selected_opportunity" in state else "wait_for_selection"
)
workflow.add_edge("extract_context", "generate_response")
workflow.add_edge("generate_response", "save_pdf")
workflow.set_finish_point("save_pdf")

app_graph = workflow.compile()

@app.post("/rfp-assistant/start")
async def start_rfp_flow(
    company_name: str = Form(...),
    company_description: str = Form(...)
):
    initial_state = {
        "company_profile": CompanyProfile(name=company_name, description=company_description)
    }
    session_id = create_state(initial_state)

    state = get_state(session_id)
    state = app_graph.invoke(state)
    update_state(session_id, state)

    opportunities = state.get("all_opportunities", [])
    # opportunities_summary = [
    #     {"title": opp.title, "description": opp.description, "match_score": opp.match_score}
    #     for opp in opportunities
    # ]

    return {"session_id": session_id, "opportunities": opportunities}


@app.post("/rfp-assistant/continue")
async def continue_rfp_flow(
    session_id: str = Form(...),
    selected_opportunity_index: int = Form(...),
    rfp_file: Optional[UploadFile] = File(None)
):
    state = get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    opportunities = state.get("all_opportunities", [])
    if not (0 < selected_opportunity_index <= len(opportunities)):
        raise HTTPException(status_code=400, detail="Invalid opportunity index")

    state["selected_opportunity"] = opportunities[selected_opportunity_index-1]
    if rfp_file:
        state["rfp_file"] = rfp_file

    update_state(session_id, state)

    # Resume from wait_for_opportunity_selection pause
    state = app_graph.invoke(state)
    update_state(session_id, state)

    return FileResponse(state["rfp_pdf_path"], media_type="application/pdf", filename="rfp_response.pdf")


@app.post("/rfp-assistant/status")
async def get_status(session_id: str = Form(...)):
    state = get_state(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "has_opportunities": "all_opportunities" in state,
        "selected_opportunity": state.get("selected_opportunity", {}).get("title"),
        "rfp_pdf_generated": "rfp_pdf_path" in state,
        "awaiting_user_input": "selected_opportunity" not in state,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app=app, host="0.0.0.0", port=5007)
