.PHONY: data history test eval eval-region app mcp attainment attainment-dry guru guru-dry guru-chat

# Regenerate the bundled datasets (already committed; only needed to reseed).
data: history
	python generate_forecast_data.py --n 600 --seed 28 --out data/pipeline.csv

# Regenerate historical bookings + forward targets (for YoY/QoQ/MoM + attainment).
history:
	python generate_history.py --seed 42 --years 3

# Run the deterministic-core unit tests.
test:
	python -m pytest -q

# Print the evaluation scorecard (region-agnostic: one global stage norm).
eval:
	python -m detector.evaluate data/pipeline.csv

# Print the scorecard with region-aware norms (recommended for the regional data).
eval-region:
	python -m detector.evaluate data/pipeline.csv --region-aware

# Launch the two-mode Streamlit UI.
app:
	streamlit run app.py

# Run the MCP server (stdio) exposing the detector to any MCP client.
mcp:
	python mcp_server.py

# Predict risk-adjusted regional attainment: one agent per region over the MCP
# server, then a portfolio roll-up. Needs ANTHROPIC_API_KEY.
attainment:
	python -m agents.attainment --all

# Same flow with no key/network: deterministic baseline only (proves the stdio
# + tools + estimator pipeline end to end).
attainment-dry:
	python -m agents.attainment --all --dry-run

# Sales guru: recommend plays to de-risk deals and give each region's VP their
# top few things to do today (one play may cover several deals, ranked by
# ARR-at-stake). Needs ANTHROPIC_API_KEY. Pass DEAL=D-10023 to coach one deal.
guru:
	python -m agents.sales_guru $(if $(DEAL),--deal $(DEAL),--all)

# Same flow with no key/network: deterministic plays / worklist only.
guru-dry:
	python -m agents.sales_guru $(if $(DEAL),--deal $(DEAL),--all) --dry-run

# Interactive guru: ask for your top things, then keep prompting. Needs a key.
# Pass REGION=NA to seed the first question.
guru-chat:
	python -m agents.sales_guru --chat $(if $(REGION),--region $(REGION),)
