.PHONY: data history test eval eval-region app mcp attainment attainment-dry

# Regenerate the bundled datasets (already committed; only needed to reseed).
data: history
	python generate_forecast_data.py --n 600 --seed 42 --out data/pipeline.csv

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
