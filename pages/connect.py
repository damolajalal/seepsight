    "fingerprint": st.session_state.get("connect_upload_fingerprint"),
    "company_id": str(company_id),
    "company_name": company_name,
    "currency": currency,
    "kinds": sorted(kinds.items()),
    "mappings": selected_mappings,
}
check_signature = hashlib.sha256(repr(signature_payload).encode("utf-8")).hexdigest()
if st.session_state.get("connect_check_signature") != check_signature:
    st.session_state.pop("connect_check", None)
    st.session_state.pop("_done", None)

st.markdown("### Step 4. Validate your procurement records")
st.caption("The check uses the mappings shown above. Review uncertain matches before proceeding.")

if st.button("Validate and analyse records", type="primary", use_container_width=True, key="run_connect_check"):
    config = {"currency": currency}
    try:
        with st.spinner("Recognising fields, validating records and running available checks..."):
            if single_file:
                filename = next(iter(core_files))
                result = engine.onboard(
                    df=raw[filename],
                    overrides=mapping_overrides,
                    config=config,
                    verbose=False,
                )
            else:
                tables = {}
                table_overrides = {}
                for filename, kind in core_files.items():
                    tables[kind] = raw[filename]
                    table_overrides[kind] = mapping_overrides.get(kind, {})
                result = engine.onboard_tables(
                    tables,
                    overrides=table_overrides,
                    config=config,
                    verbose=False,
                )
        st.session_state["connect_check"] = result
        st.session_state["connect_check_signature"] = check_signature
        st.session_state.pop("_done", None)
    except Exception as exc:
        st.error(f"We could not validate these records: {exc}")
        st.stop()

result = st.session_state.get("connect_check")
if result and st.session_state.get("connect_check_signature") == check_signature:
    quality = result.get("quality", {})
    st.markdown("### Step 5. Review validation results")

    if result.get("stopped"):
        st.error(result["stopped"])
        missing = result.get("needs_choice", [])
        if missing:
            st.write("Fields still requiring a match: " + ", ".join(plain.FIELD_LABELS.get(field, field) for field in missing))
    else:
        rows_in = int(quality.get("rows_in_file", 0) or 0)
        rows_used = int(quality.get("rows_used", 0) or 0)
        st.success(f"Validation completed: {rows_used:,} of {rows_in:,} order rows are available for analysis.")

        dropped = quality.get("dropped", {})
        if dropped:
            for reason, count in dropped.items():
                if count:
                    st.write(f"• {str(reason).replace('_', ' ').capitalize()}: {count:,}")

        warnings = quality.get("warnings", [])
        if warnings:
            st.markdown("**Items to review**")
            for warning in warnings:
                st.warning(warning)
        else:
            st.write("No additional data-quality warnings were returned by the current checks.")

        st.markdown("**Available procurement checks**")
        for detector, status in quality.get("detectors", {}).items():
            label = plain.CHECK_LABELS.get(detector, detector)
            if status == "ready":
                st.write(f"✓ {label} — ready")
            else:
                st.write(f"• {label} — not ready: {status}")

        with st.expander("Review confirmed column mappings"):
            mapping_rows = []
            for field, info in result.get("mapping", {}).items():
                mapping_rows.append({
                    "Seepsight field": plain.FIELD_LABELS.get(field.split(".")[-1], field),
                    "Source column": info.get("column"),
                    "Confidence": f"{float(info.get('confidence', 0)):.0%}",
                    "Mapping source": info.get("source", "automatic"),
                })
            if mapping_rows:
                st.dataframe(pd.DataFrame(mapping_rows), hide_index=True, width="stretch")
            else:
                st.info("No column mappings were returned.")

        if supplemental:
            st.info(
                "Remember: additional recognised datasets listed above have not been "
                "included in this analysis yet. Only the supported core datasets were processed."
            )

        st.markdown("### Step 6. Open your company workspace")
        st.caption("Your results will be attached to the signed-in company identity shown at the top of this page.")
        if st.button("Review procurement intelligence", type="primary", use_container_width=True, key="open_company_workspace"):
            try:
                with st.status("Preparing your company procurement workspace...", expanded=True) as status:
                    st.write("Using the validated procurement records")
                    st.write("Preparing findings and supporting evidence")
                    pack = workspace.from_result(result, company_name, company_id)
                    st.session_state["mine"] = pack
                    status.update(label="Your procurement review is ready", state="complete")
                st.session_state["_ws_next"] = "mine"
                st.session_state["_done"] = True
                st.rerun()
            except Exception as exc:
                st.error(f"We could not prepare your workspace: {exc}")

if st.session_state.get("_done"):
    st.success("Your review is ready. Open Overview in the navigation menu to view your procurement intelligence.")
