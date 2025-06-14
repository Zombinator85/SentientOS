# GitHub Bridge

`github_bridge.py` provides a tiny wrapper around [ghapi](https://github.com/fastai/ghapi).
Tokens are stored in the system keyring and validated for the scopes you request.
No token value is ever logged or sent to a language model.

Run the Streamlit dashboard to configure tokens. A simpler GUI composer and PR wizard is also available:

```bash
streamlit run github_dashboard.py
```
```bash
streamlit run github_gui.py
```

Enter a model name, your personal access token and a comma separated list of
required scopes. Press **Test & Save**. The bridge verifies the token by
calling `GET /user` via ghapi and checking the `X-OAuth-Scopes` header. If the
required scopes are present the token is saved in the keyring.

Once saved you can search code, open issues and create pull requests through the
GUI, respecting the selected checkboxes for read, write and PR actions.
