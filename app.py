"""
YumBurger — Streamlit demo UI
Talks to the FastAPI connector on http://localhost:8000
Run: streamlit run app.py
"""

import time
import requests
import streamlit as st

# CONNECTOR = "http://localhost:8000"
CONNECTOR = "http://yumburger-connector-416434018.us-east-1.elb.amazonaws.com"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="YumBurger Analytics",
    page_icon="🍔",
    layout="wide",
)

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 8])
with col_logo:
    try:
        st.image("assets/logo_yumburger.png", width=80)
    except Exception:
        st.markdown("🍔")
with col_title:
    st.title("YumBurger Analytics")
    st.caption("Governed NL→SQL · Iceberg Silver Zone · Lake Formation")

st.divider()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Settings")
    persona = st.selectbox("Persona", ["analyst", "admin"], index=0)
    max_rows = st.slider("Max rows", 5, 100, 20)

    st.divider()

    # Health check
    try:
        health = requests.get(f"{CONNECTOR}/health", timeout=3).json()
        st.success(f"Connector: {health['status']}")
    except Exception:
        st.error("Connector offline — run `python -m connector.main`")

    st.divider()

    # Allowed tables
    try:
        tables = requests.get(f"{CONNECTOR}/tables", timeout=3).json()["tables"]
        st.markdown("**Tables**")
        for t in tables:
            st.markdown(f"- `{t}`")
    except Exception:
        pass

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_query, tab_explore, tab_ontology = st.tabs(["💬 Ask a Question", "🗂 Explore Tables", "🔗 Ontology"])

# ── Tab 1: NL Query ───────────────────────────────────────────────────────────
with tab_query:
    st.subheader("Ask anything about YumBurger data")

    example_questions = [
        "How many active suppliers do we have?",
        "What are the top 5 most expensive menu items?",
        "What is the total revenue by region?",
        "How many customers are in each loyalty tier?",
        "What is the average order value by channel?",
        "Which menu items contain gluten?",
        "Show me the top 10 customers by lifetime spend",
        "How many orders came through the Mobile App channel?",
    ]

    selected = st.selectbox("Pick an example", ["— custom —"] + example_questions)
    question = st.text_input(
        "Your question",
        value="" if selected == "— custom —" else selected,
        placeholder="e.g. How many active suppliers are there?",
    )

    if st.button("Ask", type="primary", disabled=not question):
        with st.spinner("Compiling SQL and querying Athena…"):
            t0 = time.time()
            try:
                resp = requests.post(
                    f"{CONNECTOR}/query",
                    json={"question": question, "persona": persona, "max_rows": max_rows},
                    timeout=120,
                )
                elapsed = time.time() - t0

                if resp.status_code == 200:
                    data = resp.json()

                    # Metrics row
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Rows returned", data["row_count"])
                    m2.metric("Duration", f"{data['duration_ms']} ms")
                    m3.metric("Persona", data["persona"])
                    m4.metric("Request ID", data["request_id"][:8] + "…")

                    # Generated SQL
                    with st.expander("Generated SQL", expanded=True):
                        st.code(data["compiled_sql"], language="sql")

                    # Results table
                    if data["rows"]:
                        st.dataframe(data["rows"], use_container_width=True)
                    else:
                        st.info("Query returned no rows.")

                elif resp.status_code == 422:
                    st.warning(f"Query rejected by compiler: {resp.json().get('detail')}")
                else:
                    st.error(f"Error {resp.status_code}: {resp.json().get('detail')}")

            except requests.exceptions.ConnectionError:
                st.error("Cannot reach connector. Is `python -m connector.main` running?")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

# ── Tab 2: Table Explorer ─────────────────────────────────────────────────────
with tab_explore:
    st.subheader("Iceberg Table Schemas & Snapshots")

    try:
        tables_resp = requests.get(f"{CONNECTOR}/tables", timeout=5).json()
        table_choice = st.selectbox("Select table", tables_resp["tables"], key="explore_table")

        col_schema, col_snaps = st.columns(2)

        with col_schema:
            st.markdown(f"**Schema — `{table_choice}`**")
            with st.spinner("Loading schema…"):
                meta = requests.get(f"{CONNECTOR}/metadata/{table_choice}", timeout=30).json()
            # Parse DESCRIBE output into clean rows
            rows = [
                {"column": r.get("col_name", ""), "type": r.get("data_type", "")}
                for r in meta["columns"]
                if r.get("col_name", "").strip() and not r.get("col_name", "").startswith("#")
            ]
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            else:
                st.write(meta["columns"])

        with col_snaps:
            st.markdown(f"**Snapshots — `{table_choice}`**")
            with st.spinner("Loading snapshots…"):
                snaps = requests.get(f"{CONNECTOR}/snapshots/{table_choice}", timeout=30).json()
            if snaps["snapshots"]:
                snap_rows = [
                    {
                        "snapshot_id": s.get("snapshot_id", ""),
                        "committed_at": s.get("committed_at", ""),
                        "operation": s.get("operation", ""),
                        "added_records": s.get("added_records", ""),
                    }
                    for s in snaps["snapshots"]
                ]
                st.dataframe(snap_rows, use_container_width=True, hide_index=True)
            else:
                st.info("No snapshots yet.")

    except requests.exceptions.ConnectionError:
        st.error("Connector offline.")
    except Exception as e:
        st.error(f"Error: {e}")

# ── Tab 3: Ontology ───────────────────────────────────────────────────────────
with tab_ontology:
    st.subheader("Semantic Ontology")

    try:
        col_classes, col_props = st.columns(2)

        with col_classes:
            st.markdown("**Classes**")
            classes = requests.get(f"{CONNECTOR}/ontology/classes", timeout=30).json()
            class_rows = [
                {
                    "uri": c.get("class_uri", ""),
                    "label": c.get("label", ""),
                    "maps_to": c.get("maps_to_table", ""),
                }
                for c in classes
            ]
            st.dataframe(class_rows, use_container_width=True, hide_index=True)

        with col_props:
            st.markdown("**Properties**")
            props = requests.get(f"{CONNECTOR}/ontology/properties", timeout=30).json()
            prop_rows = [
                {
                    "uri": p.get("property_uri", ""),
                    "label": p.get("label", ""),
                    "maps_to_column": p.get("maps_to_column", ""),
                }
                for p in props
            ]
            st.dataframe(prop_rows, use_container_width=True, hide_index=True)

    except requests.exceptions.ConnectionError:
        st.error("Connector offline.")
    except Exception as e:
        st.error(f"Error: {e}")
