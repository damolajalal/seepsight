"""Company database connection management UI."""

import uuid
import streamlit as st

from seepsight import database_connectors, firestore_db


def render_company_database_connections(company_id, account):
    """Render owner-managed database connections inside Connect Your Data."""
    if not company_id:
        st.info("Sign in to manage company database connections.")
        return
    if not isinstance(account, dict) or account.get("role") != "owner":
        st.info("Only the company owner can add, test or disable database connections.")
        return
    st.markdown("### Company database connections")
    account = st.session_state.get("seepsight_auth")
    if not isinstance(account, dict) or not account.get("company_id"):
        st.info("Sign in to manage company database connections.")
    elif account.get("role") != "owner":
        st.info("Only the company owner can add, test or disable database connections.")
    else:
        company_id = account["company_id"]
        st.write(
            "Connection credentials stay in Google Secret Manager. Seepsight stores "
            "only the Secret Manager resource reference and connection metadata."
        )
        with st.expander("Add a database connection", expanded=False):
            with st.form("add_company_database_connection"):
                connection_name = st.text_input("Connection name", max_chars=120)
                provider = st.selectbox(
                    "Database provider",
                    ["postgres", "mysql", "sqlserver", "bigquery"],
                    format_func=lambda value: {
                        "postgres": "PostgreSQL",
                        "mysql": "MySQL",
                        "sqlserver": "Microsoft SQL Server",
                        "bigquery": "Google BigQuery",
                    }[value],
                )
                secret_reference = st.text_input(
                    "Secret Manager secret-version resource",
                    placeholder="projects/PROJECT_ID/secrets/SECRET_NAME/versions/latest",
                )
                database_name = st.text_input("Database (optional)", max_chars=128)
                schema_name = st.text_input("Schema or dataset (optional)", max_chars=128)
                description = st.text_input("Description (optional)", max_chars=300)
                max_rows = st.number_input(
                    "Maximum rows returned per query",
                    min_value=1, max_value=1000, value=500, step=25,
                )
                timeout_seconds = st.number_input(
                    "Query timeout (seconds)",
                    min_value=1, max_value=60, value=15, step=1,
                )
                submitted = st.form_submit_button(
                    "Save connection profile",
                    use_container_width=True,
                    disabled=bool(st.session_state.get("seepsight_demo_mode")),
                )
            if st.session_state.get("seepsight_demo_mode"):
                st.caption("Saving new or changing saved profiles is paused during the session-only demo.")
            if submitted:
                try:
                    connection_id = uuid.uuid4().hex
                    firestore_db.save_company_connection_profile(
                        company_id,
                        connection_id,
                        {
                            "name": connection_name,
                            "provider": provider,
                            "secret_reference": secret_reference,
                            "database": database_name,
                            "schema": schema_name,
                            "description": description,
                            "max_rows": int(max_rows),
                            "timeout_seconds": int(timeout_seconds),
                        },
                    )
                    st.success("Connection profile saved. Test it below to verify Secret Manager access and database connectivity.")
                    st.rerun()
                except (TypeError, ValueError, PermissionError) as exc:
                    st.error(str(exc))
                except Exception:
                    st.error("The connection profile could not be saved. Please try again.")
    
        try:
            profiles = firestore_db.get_company_connection_profiles(company_id)
        except Exception:
            profiles = None
            st.error("Company connection profiles could not be loaded.")
        if profiles is not None:
            if not profiles:
                st.caption("No database connections have been added.")
            for profile in profiles:
                connection_id = profile.get("connection_id") or profile.get("id")
                name = profile.get("name", "Unnamed connection")
                provider_name = profile.get("provider", "unknown")
                status = profile.get("status", "inactive")
                with st.container(border=True):
                    left, right = st.columns([3, 1])
                    with left:
                        st.write(f"**{name}**")
                        st.caption(
                            f"{provider_name} · {profile.get('database') or 'Database not specified'} · "
                            f"{status}"
                        )
                        if profile.get("description"):
                            st.caption(profile["description"])
                    with right:
                        if status == "active":
                            if st.button(
                                "Test connection",
                                key=f"test_connection_{connection_id}",
                                use_container_width=True,
                            ):
                                try:
                                    result = database_connectors.execute_company_connection_query(
                                        company_id, connection_id,
                                        "SELECT 1 AS seepsight_connection_test",
                                        audit=not st.session_state.get("seepsight_demo_mode"),
                                    )
                                    st.success(
                                        f"Connection successful. {result['row_count']} test row returned."
                                    )
                                except Exception:
                                    st.error(
                                        "Connection test failed. Check the Secret Manager reference, "
                                        "runtime permissions, network access and read-only database credentials."
                                    )
                            if st.button(
                                "Disable",
                                key=f"disable_connection_{connection_id}",
                                use_container_width=True,
                                disabled=bool(st.session_state.get("seepsight_demo_mode")),
                            ):
                                try:
                                    firestore_db.set_company_connection_profile_status(
                                        company_id, connection_id, "inactive"
                                    )
                                    st.rerun()
                                except Exception:
                                    st.error("The connection could not be disabled.")
                        else:
                            if st.button(
                                "Enable",
                                key=f"enable_connection_{connection_id}",
                                use_container_width=True,
                                disabled=bool(st.session_state.get("seepsight_demo_mode")),
                            ):
                                try:
                                    firestore_db.set_company_connection_profile_status(
                                        company_id, connection_id, "active"
                                    )
                                    st.rerun()
                                except Exception:
                                    st.error("The connection could not be enabled.")
    
