with st.sidebar:
    st.header("🔐 Zerodha Token Generator")

    # Step 1: Show login URL
    try:
        kite = KiteConnect(api_key=API_KEY)
        login_url = kite.login_url()
        st.markdown("👉 [Click here to login to Zerodha](%s)" % login_url)
    except Exception as e:
        st.error(f"Error generating login URL: {e}")

    # Step 2: Paste request_token
    st.write("Paste the `request_token` you get after login:")
    req_token = st.text_input("Request Token")

    # Step 3: Generate access token
    if st.button("Generate Access Token"):
        try:
            data = kite.generate_session(req_token, api_secret=API_SECRET)
            access_token = data["access_token"]
            sheet.update_acell("B2", access_token)
            st.success("✅ Access token updated successfully!")
        except Exception as e:
            st.error(f"❌ Failed to generate access token: {e}")
