"""Forecast Anomaly Detector: deterministic RevOps deal-risk rules.

The deterministic core (:mod:`detector.rules`, :mod:`detector.engine`,
:mod:`detector.evaluate`) makes zero network calls. Only
:mod:`detector.narrative` touches an external API, and it degrades to a no-op
when no key is configured.
"""
