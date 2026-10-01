# Natal release regression checks

Run `python tests/run_natal_checks.py` with the calculation and HTTP dependencies
listed in `.github/workflows/natal-checks.yml`. The Linux workflow uses the same
`pyswisseph==2.10.3.2` binding as production. Windows checks may use `pysweph`;
the test adapter removes its extra dummy cusp and does not change application code.

Run `node tests/test_geo_form.cjs` to check both engine forms.
Run `node tests/test_klassika_page.cjs /path/to/quantareon-site/razbor-ru.html`
to check the separately deployed website page.

The tests replace LLM, geocoding, storage, mail and Telegram transports. The actual
cash workflow, birth calculation, chart export, worker and HTTP delivery run
locally. No real payments, paid LLM calls or customer messages are sent.
