import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# ============================================================
# PROJECT CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.pdf_processor import process_pdf
from src.rag.vector_store import get_collection, store_chunks
from src.rag.claude_assistant import ask_solicitation
from src.database import fetch_all


REPORTS_DIR = PROJECT_ROOT / "data" / "reports"
SOLICITATIONS_DIR = PROJECT_ROOT / "data" / "solicitations"

SOLICITATIONS_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="GovCon BD Intelligence Platform",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CSV INTELLIGENCE DATA
# ============================================================

def find_latest_report(pattern):
    """Find the newest report matching a filename pattern."""

    files = list(REPORTS_DIR.glob(pattern))

    if not files:
        return None

    return max(
        files,
        key=lambda file: file.stat().st_mtime
    )


@st.cache_data(show_spinner=False)
def load_csv_file(file_path, modified_time):
    """Load a CSV report without changing the source file."""

    return pd.read_csv(
        file_path,
        dtype=str,
        keep_default_na=False
    )


def load_bd_intelligence():
    """Load the latest consolidated BD classification report."""

    report = find_latest_report(
        "sam_opportunity_bd_classification_*.csv"
    )

    if report is None:
        return None

    return load_csv_file(
        str(report),
        report.stat().st_mtime
    )


def load_bid_recommendations():
    """Load the latest Bid/No-Bid recommendation report."""

    report = find_latest_report(
        "sam_bid_no_bid_recommendations_*.csv"
    )

    if report is None:
        return None

    return load_csv_file(
        str(report),
        report.stat().st_mtime
    )


def safe_number(value, default=0):
    """Safely convert report values to numbers."""
    try:
        if value is None or pd.isna(value):
            return default

        cleaned = str(value).strip().replace(",", "").replace("$", "")
        if not cleaned:
            return default

        number = pd.to_numeric(cleaned, errors="coerce")
        if pd.isna(number):
            return default

        return float(number)
    except (ValueError, TypeError):
        return default


def display_number(value):
    return f"{safe_number(value):,.0f}"


def display_sources(sources):
    """Display source citations returned by Claude."""

    if not sources:
        st.info("No source references were returned.")
        return

    st.markdown("#### Sources")

    for source in sources:
        filename = source.get("filename") or "Unknown file"
        page = source.get("page_number")
        st.markdown(f"- **{filename}** — Page {page}")


# ============================================================
# PDF AND RAG FUNCTIONS
# ============================================================

def get_indexed_documents():
    """Return indexed document names and passage counts."""

    collection = get_collection()
    records = collection.get(include=["metadatas"])

    counts = {}

    for metadata in records.get("metadatas", []):
        if metadata and metadata.get("document_id"):
            document_id = metadata["document_id"]

            counts[document_id] = (
                counts.get(document_id, 0) + 1
            )

    return counts


def ingest_uploaded_pdf(uploaded_file):
    """Save and index an uploaded PDF."""

    safe_name = Path(uploaded_file.name).name

    if not safe_name.lower().endswith(".pdf"):
        raise ValueError("Please upload a PDF file.")

    file_bytes = uploaded_file.getvalue()

    if not file_bytes:
        raise ValueError("The uploaded file is empty.")

    if not file_bytes.startswith(b"%PDF-"):
        raise ValueError("The file does not appear to be a valid PDF.")

    pdf_path = SOLICITATIONS_DIR / safe_name

    pdf_path.write_bytes(file_bytes)

    result = process_pdf(pdf_path)

    if not result.get("chunks"):
        raise ValueError(
            "No text chunks were extracted. "
            "The PDF may be scanned or contain no extractable text."
        )

    stored_count = store_chunks(
        chunks=result["chunks"],
        document_id=pdf_path.name,
    )

    return {
        "filename": pdf_path.name,
        "pages": result.get("page_count", 0),
        "chunks": len(result["chunks"]),
        "stored": stored_count,
        "document_id": pdf_path.name,
    }


# ============================================================
# POSTGRESQL READ-ONLY FUNCTIONS
# ============================================================

def load_postgres_opportunities():
    """Read opportunities from PostgreSQL. No database writes."""

    return fetch_all(
        """
        SELECT
            opportunity_id,
            source_name,
            source_record_id,
            solicitation_number,
            title,
            agency_name,
            opportunity_type,
            description,
            naics_code,
            set_aside_type,
            place_of_performance,
            estimated_value,
            posted_date,
            response_deadline,
            status,
            source_url,
            is_sample_data,
            updated_at
        FROM public.opportunities
        ORDER BY
            posted_date DESC NULLS LAST,
            opportunity_id DESC
        """
    )


# ============================================================
# SHARED DISPLAY FUNCTIONS
# ============================================================

def show_opportunity_details(df, key):
    """Show details for a selected opportunity."""

    if df.empty:
        st.info("No opportunities available.")
        return

    options = []

    for index, row in df.iterrows():
        title = row.get("title", "Untitled")
        notice_id = row.get("notice_id", index)

        options.append(
            f"{title} | {notice_id}"
        )

    selected = st.selectbox(
        "Select an opportunity",
        options=options,
        key=key,
    )

    selected_index = options.index(selected)
    row = df.iloc[selected_index]

    st.markdown("### Opportunity Details")

    fields = [
        ("Title", "title"),
        ("Notice ID", "notice_id"),
        ("Solicitation Number", "solicitation_number"),
        ("Agency", "agency"),
        ("Notice Type", "notice_type"),
        ("NAICS", "naics_code"),
        ("Set-Aside", "set_aside"),
        ("Posted Date", "posted_date"),
        ("Response Deadline", "response_deadline"),
        ("Place of Performance", "place_of_performance"),
        ("BD Classification", "bd_classification"),
        ("Qualification Score", "qualification_total_score"),
        ("Relevance Score", "relevance_v2_score"),
        ("Bid Decision", "bid_no_bid_decision"),
    ]

    for label, column in fields:
        if column in row.index:
            value = row.get(column, "")
            st.write(f"**{label}:** {value or 'Not provided'}")

    if "source_url" in row.index:
        source_url = row.get("source_url", "")

        if source_url:
            st.link_button(
                "Open Official Opportunity Source",
                source_url
            )

    with st.expander("Full opportunity description"):
        st.write(
            row.get("description_text")
            or "No description available."
        )

    with st.expander("Qualification and BD reasoning"):
        for column in [
            "classification_reason",
            "capability_fit_reason",
            "pursuit_readiness_reason",
            "bd_classification_reason",
            "v2_reason",
            "decision_reason",
            "decision_review_flags",
        ]:
            if column in row.index:
                value = row.get(column, "")

                if value:
                    st.markdown(f"**{column.replace('_', ' ').title()}**")
                    st.write(value)


# ============================================================
# DASHBOARD
# ============================================================

def display_dashboard(df, recommendations):

    st.title("📊 GovCon BD Intelligence Dashboard")

    st.markdown(
        """
        **Tiger Team Engineering** | Federal Government Contracting
        Business Development Intelligence

        Developed by **Abdul Samad**  
        *GovCon BD Intelligence & AI Automation Developer*
        """
    )

    if df is None or df.empty:
        st.warning(
            "The BD classification report was not found. "
            "Run the discovery and classification pipeline first."
        )
        return

    total = len(df)

    direct = (
        df["bd_classification"]
        .str.lower()
        .eq("direct tte")
        .sum()
        if "bd_classification" in df.columns else 0
    )

    potential_direct = (
        df["bd_classification"]
        .str.lower()
        .eq("potential direct")
        .sum()
        if "bd_classification" in df.columns else 0
    )

    teaming = (
        df["bd_classification"]
        .str.lower()
        .str.contains("teaming", na=False)
        .sum()
        if "bd_classification" in df.columns else 0
    )

    insufficient = (
        df["bd_classification"]
        .str.lower()
        .str.contains("insufficient", na=False)
        .sum()
        if "bd_classification" in df.columns else 0
    )
    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total Opportunities", f"{total:,}")
    col2.metric("Direct TTE", f"{direct:,}")
    col3.metric("Potential Direct", f"{potential_direct:,}")
    col4.metric("Teaming", f"{teaming:,}")
    col5.metric("Insufficient Evidence", f"{insufficient:,}")

    st.divider()

    left, right = st.columns(2)

    with left:
        st.subheader("BD Classification")

        if "bd_classification" in df.columns:
            classification_counts = (
                df["bd_classification"]
                .replace("", "Unclassified")
                .value_counts()
            )

            st.bar_chart(classification_counts)

    with right:
        st.subheader("Bid / No-Bid Decisions")

        if recommendations is not None and not recommendations.empty:
            decision_column = (
                "bid_no_bid_decision"
                if "bid_no_bid_decision" in recommendations.columns
                else None
            )

            if decision_column:
                decision_counts = (
                    recommendations[decision_column]
                    .replace("", "Unclassified")
                    .value_counts()
                )

                st.bar_chart(decision_counts)
            else:
                st.info(
                    "The recommendation report does not contain "
                    "the expected decision column."
                )
        else:
            st.info("Bid / No-Bid recommendation report not found.")

    st.divider()

    st.subheader("NAICS Distribution")

    if "naics_code" in df.columns:
        naics_counts = (
            df["naics_code"]
            .replace("", "Not provided")
            .value_counts()
            .head(10)
        )

        st.bar_chart(naics_counts)

    st.subheader("Latest BD Intelligence Records")

    display_columns = [
        column for column in [
            "title",
            "agency",
            "naics_code",
            "notice_type",
            "bd_classification",
            "bd_confidence",
            "relevance_v2_score",
        ]
        if column in df.columns
    ]

    if display_columns:
        st.dataframe(
            df[display_columns].head(20),
            use_container_width=True,
            hide_index=True,
        )

    st.caption(
        "This dashboard is based on the latest local BD classification "
        "and Bid/No-Bid report files."
    )


# ============================================================
# OPPORTUNITY PIPELINE
# ============================================================

def display_opportunity_pipeline(df):

    st.title("🔎 Opportunity Pipeline")

    st.write(
        "Explore discovered federal opportunities, review their "
        "business development classification, and identify records "
        "that need further research."
    )

    if df is None or df.empty:
        st.warning("No BD intelligence report is available.")
        return

    filtered = df.copy()

    filter_columns = st.columns(3)

    with filter_columns[0]:
        if "bd_classification" in filtered.columns:
            classifications = sorted(
                filtered["bd_classification"]
                .replace("", "Unclassified")
                .unique()
                .tolist()
            )

            selected_classifications = st.multiselect(
                "BD Classification",
                classifications,
                default=classifications,
            )

            filtered = filtered[
                filtered["bd_classification"]
                .replace("", "Unclassified")
                .isin(selected_classifications)
            ]

    with filter_columns[1]:
        if "naics_code" in filtered.columns:
            naics_values = sorted(
                filtered["naics_code"]
                .replace("", "Not provided")
                .unique()
                .tolist()
            )

            selected_naics = st.multiselect(
                "NAICS Code",
                naics_values,
                default=naics_values,
            )

            filtered = filtered[
                filtered["naics_code"]
                .replace("", "Not provided")
                .isin(selected_naics)
            ]

    with filter_columns[2]:
        if "notice_type" in filtered.columns:
            notice_types = sorted(
                filtered["notice_type"]
                .replace("", "Not provided")
                .unique()
                .tolist()
            )

            selected_types = st.multiselect(
                "Notice Type",
                notice_types,
                default=notice_types,
            )

            filtered = filtered[
                filtered["notice_type"]
                .replace("", "Not provided")
                .isin(selected_types)
            ]

    search_text = st.text_input(
        "Search title, agency, description, or notice ID"
    )

    if search_text:
        searchable_columns = [
            column for column in [
                "title",
                "agency",
                "description_text",
                "notice_id",
                "solicitation_number",
            ]
            if column in filtered.columns
        ]

        if searchable_columns:
            mask = pd.Series(
                False,
                index=filtered.index
            )

            for column in searchable_columns:
                mask |= (
                    filtered[column]
                    .astype(str)
                    .str.contains(
                        search_text,
                        case=False,
                        na=False,
                        regex=False,
                    )
                )

            filtered = filtered[mask]

    st.metric("Matching Opportunities", f"{len(filtered):,}")

    display_columns = [
        column for column in [
            "title",
            "agency",
            "notice_type",
            "naics_code",
            "set_aside",
            "response_deadline",
            "bd_classification",
            "bd_confidence",
            "relevance_v2_score",
            "qualification_total_score",
        ]
        if column in filtered.columns
    ]

    st.dataframe(
        filtered[display_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download Filtered Opportunities CSV",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="tte_filtered_opportunities.csv",
        mime="text/csv",
    )

    st.divider()

    show_opportunity_details(
        filtered,
        key="pipeline_opportunity_selector",
    )


# ============================================================
# BID / NO-BID ANALYSIS
# ============================================================

def display_bid_analysis(recommendations):

    st.title("⚖️ Bid / No-Bid Analysis")

    st.write(
        "Review conservative bid recommendations generated from "
        "the opportunity qualification and BD classification pipeline."
    )

    if recommendations is None or recommendations.empty:
        st.warning(
            "No Bid / No-Bid recommendation report found. "
            "Run scripts/recommend_bid_no_bid.py first."
        )
        return

    decision_column = (
        "bid_no_bid_decision"
        if "bid_no_bid_decision" in recommendations.columns
        else None
    )

    if decision_column is None:
        st.error(
            "The recommendation report is missing "
            "the bid_no_bid_decision column."
        )
        st.dataframe(recommendations.head(20))
        return

    decisions = (
        recommendations[decision_column]
        .fillna("")
        .astype(str)
        .str.upper()
    )

    bid_count = decisions.eq("BID").sum()
    no_bid_count = decisions.eq("NO-BID").sum()
    teaming_count = decisions.eq("TEAMING").sum()
    review_count = decisions.eq("REVIEW").sum()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("BID", f"{bid_count:,}")
    col2.metric("NO-BID", f"{no_bid_count:,}")
    col3.metric("TEAMING", f"{teaming_count:,}")
    col4.metric("REVIEW", f"{review_count:,}")

    st.info(
        "A BID recommendation is not an authorization to submit. "
        "Verify the official solicitation, eligibility, requirements, "
        "deadline, pricing, and internal capacity before pursuing."
    )

    st.divider()

    selected_decisions = st.multiselect(
        "Filter by decision",
        sorted(decisions.unique().tolist()),
        default=sorted(decisions.unique().tolist()),
    )

    filtered = recommendations[
        decisions.isin(selected_decisions)
    ].copy()

    display_columns = [
        column for column in [
            "title",
            "agency",
            "naics_code",
            "notice_type",
            "response_deadline",
            "bd_classification",
            "qualification_total_score",
            "relevance_v2_score",
            "bid_no_bid_decision",
            "decision_reason",
            "decision_review_flags",
        ]
        if column in filtered.columns
    ]

    st.dataframe(
        filtered[display_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download Bid / No-Bid Report",
        data=filtered.to_csv(index=False).encode("utf-8"),
        file_name="tte_bid_no_bid_analysis.csv",
        mime="text/csv",
    )

    st.divider()

    show_opportunity_details(
        filtered,
        key="bid_analysis_opportunity_selector",
    )


# ============================================================
# GOVERNMENT OPPORTUNITIES — POSTGRESQL
# ============================================================

def display_government_opportunities():

    st.title("🏛️ Government Opportunities")

    st.write(
        "Browse the opportunities stored in the project's PostgreSQL "
        "database. This page uses read-only database access."
    )

    try:
        records = load_postgres_opportunities()

        if records is None or len(records) == 0:
            st.info("No opportunities were returned from PostgreSQL.")
            return

        if isinstance(records, pd.DataFrame):
            df = records.copy()
        else:
            df = pd.DataFrame(records)

        st.metric("Database Opportunities", f"{len(df):,}")

        if "is_sample_data" in df.columns:
            sample_count = (
                df["is_sample_data"]
                .astype(str)
                .str.lower()
                .isin(["true", "1", "yes"])
                .sum()
            )

            real_count = len(df) - sample_count

            col1, col2 = st.columns(2)
            col1.metric("Real Records", f"{real_count:,}")
            col2.metric("Sample Records", f"{sample_count:,}")

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download PostgreSQL Opportunities CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="tte_postgresql_opportunities.csv",
            mime="text/csv",
        )

        with st.expander("Database record details"):
            if not df.empty:
                selected_index = st.selectbox(
                    "Select database record",
                    options=list(df.index),
                    format_func=lambda index: (
                        f"{df.loc[index].get('title', 'Untitled')} "
                        f"| ID {df.loc[index].get('opportunity_id', index)}"
                    ),
                )

                st.json(
                    df.loc[selected_index].fillna("").to_dict()
                )

    except Exception as exc:
        st.error("Could not load opportunities from PostgreSQL.")
        st.exception(exc)


# ============================================================
# SOLICITATION UPLOAD AND INGESTION
# ============================================================

def display_solicitation_upload():

    st.title("📄 Upload Solicitation")

    st.write(
        "Upload a federal solicitation PDF to extract its text, "
        "split it into searchable passages, and store those passages "
        "in the project's ChromaDB collection."
    )

    uploaded_file = st.file_uploader(
        "Choose a solicitation PDF",
        type=["pdf"],
        key="solicitation_pdf_uploader",
    )

    if uploaded_file is not None:
        st.info(
            f"Selected file: {uploaded_file.name} "
            f"({uploaded_file.size:,} bytes)"
        )

        if st.button(
            "Process and Index PDF",
            type="primary",
            key="process_solicitation_button",
        ):
            try:
                with st.spinner(
                    "Extracting PDF text and indexing passages..."
                ):
                    result = ingest_uploaded_pdf(uploaded_file)

                st.success("Solicitation successfully processed.")

                col1, col2, col3 = st.columns(3)
                col1.metric("Pages", result["pages"])
                col2.metric("Extracted Chunks", result["chunks"])
                col3.metric("Stored Chunks", result["stored"])

                st.json(result)

            except Exception as exc:
                st.error("PDF processing failed.")
                st.exception(exc)

    st.divider()

    st.subheader("Indexed Solicitation Documents")

    try:
        documents = get_indexed_documents()

        if not documents:
            st.info("No solicitation documents have been indexed yet.")
        else:
            document_df = pd.DataFrame(
                [
                    {
                        "Document": name,
                        "Indexed Passages": count,
                    }
                    for name, count in documents.items()
                ]
            )

            st.dataframe(
                document_df,
                use_container_width=True,
                hide_index=True,
            )

    except Exception as exc:
        st.error("Could not read indexed document information.")
        st.exception(exc)
        # ============================================================
# AI DOCUMENT CHAT
# ============================================================

def display_document_chat():

    st.title("🤖 AI Solicitation Assistant")

    st.write(
        "Ask questions about indexed solicitation documents. "
        "The assistant retrieves relevant passages from ChromaDB "
        "and uses Claude to generate an answer with source references."
    )

    try:
        documents = get_indexed_documents()
    except Exception as exc:
        st.error("Could not access the document index.")
        st.exception(exc)
        return

    if not documents:
        st.warning(
            "No indexed solicitation documents are available. "
            "Upload and index a PDF first."
        )
        return

    st.subheader("Available Documents")

    for filename, count in documents.items():
        st.write(f"- **{filename}** — {count} passages")

    st.divider()

    question = st.text_area(
        "Ask a question about the solicitation",
        placeholder=(
            "Example: What is the submission deadline? "
            "What technical services are required?"
        ),
        height=120,
        key="document_chat_question",
    )

    selected_document = st.selectbox(
        "Document to search",
        options=["All indexed documents"] + list(documents.keys()),
        key="document_chat_document",
    )

    if st.button(
        "Ask AI Assistant",
        type="primary",
        key="ask_document_question_button",
    ):
        if not question.strip():
            st.warning("Please enter a question.")
            return

        try:
            with st.spinner(
                "Searching indexed documents and asking Claude..."
            ):
                result = ask_solicitation(
                    question=question.strip(),
                    document_id=(
                        None
                        if selected_document == "All indexed documents"
                        else selected_document
                    ),
                )

            if isinstance(result, dict):
                answer = result.get("answer", "")
                sources = result.get("sources", [])
            else:
                answer = str(result)
                sources = []

            st.markdown("### Answer")
            st.write(answer or "The assistant returned an empty answer.")

            display_sources(sources)

        except Exception as exc:
            st.error("The AI solicitation assistant encountered an error.")
            st.exception(exc)


# ============================================================
# REQUIREMENTS ANALYSIS
# ============================================================

def display_requirements_analysis():

    st.title("📋 Solicitation Requirements Analysis")

    st.write(
        "Generate a structured analysis of an indexed solicitation. "
        "Review requirements, submission instructions, evaluation "
        "criteria, deadlines, risks, and compliance considerations."
    )

    try:
        documents = get_indexed_documents()
    except Exception as exc:
        st.error("Could not access the document index.")
        st.exception(exc)
        return

    if not documents:
        st.warning(
            "No indexed documents are available. "
            "Upload and index a solicitation PDF first."
        )
        return

    selected_document = st.selectbox(
        "Select solicitation document",
        options=list(documents.keys()),
        key="requirements_document_selector",
    )

    st.caption(
        f"Indexed passages: {documents[selected_document]}"
    )

    st.info(
        "This analysis is AI-generated. Always verify every requirement "
        "against the official solicitation and all amendments."
    )

    if st.button(
        "Analyze Solicitation Requirements",
        type="primary",
        key="analyze_requirements_button",
    ):
        analysis_question = """
        Analyze this solicitation and return a structured procurement
        requirements review.

        Identify:
        1. Solicitation title and reference number.
        2. Issuing agency and contracting office, if available.
        3. Procurement type and scope of work.
        4. Required technical services and deliverables.
        5. Mandatory qualifications, certifications, and experience.
        6. NAICS and set-aside information, if stated.
        7. Submission deadline, time zone, and submission method.
        8. Required proposal volumes and documents.
        9. Instructions to offerors and compliance requirements.
        10. Evaluation criteria and evaluation factors.
        11. Contract type, period of performance, and options.
        12. Key risks, ambiguities, and missing information.
        13. A practical compliance checklist.

        Do not invent missing details. Clearly label information that
        is not found in the indexed document. Include source page
        references wherever available.
        """

        try:
            with st.spinner(
                "Analyzing solicitation requirements with Claude..."
            ):
                result = ask_solicitation(
                    question=analysis_question,
                    document_id=selected_document,
                )

            if isinstance(result, dict):
                answer = result.get("answer", "")
                sources = result.get("sources", [])
            else:
                answer = str(result)
                sources = []

            st.markdown("### Structured Requirements Review")
            st.markdown(answer or "No analysis was returned.")

            display_sources(sources)

            st.download_button(
                "Download Requirements Analysis",
                data=(answer or "").encode("utf-8"),
                file_name="solicitation_requirements_analysis.txt",
                mime="text/plain",
            )

        except Exception as exc:
            st.error("Requirements analysis failed.")
            st.exception(exc)


# ============================================================
# APPLICATION NAVIGATION
# ============================================================

def main():

    st.sidebar.title("GovCon BD Intelligence")

    st.sidebar.markdown(
        """
        **Tiger Team Engineering**

        Federal Business Development
        Intelligence Platform
        """
    )

    st.sidebar.divider()

    page = st.sidebar.radio(
        "Navigation",
        [
            "Dashboard",
            "Opportunity Pipeline",
            "Bid / No-Bid Analysis",
            "Government Opportunities",
            "Upload Solicitation",
            "AI Document Chat",
            "Requirements Analysis",
        ],
        key="main_navigation",
    )

    st.sidebar.divider()

    st.sidebar.markdown(
        """
        **Developed by Abdul Samad**

        GovCon BD Intelligence & AI Automation Developer
        """
    )

    with st.sidebar.expander("System information"):
        st.write("**Project:** GovCon BD Intelligence Platform")
        st.write("**Database:** PostgreSQL")
        st.write("**Vector Store:** ChromaDB")
        st.write("**AI Assistant:** Claude")
        st.write("**Opportunity Source:** SAM.gov")

    df = load_bd_intelligence()
    recommendations = load_bid_recommendations()

    if page == "Dashboard":
        display_dashboard(df, recommendations)

    elif page == "Opportunity Pipeline":
        display_opportunity_pipeline(df)

    elif page == "Bid / No-Bid Analysis":
        display_bid_analysis(recommendations)

    elif page == "Government Opportunities":
        display_government_opportunities()

    elif page == "Upload Solicitation":
        display_solicitation_upload()

    elif page == "AI Document Chat":
        display_document_chat()

    elif page == "Requirements Analysis":
        display_requirements_analysis()


if __name__ == "__main__":
    main()