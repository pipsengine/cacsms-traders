"""Autonomous Trading Engine: a persistent, closed-bar state machine over the existing intelligence engines.

Market Data → Intelligence → Scanner → Structure → Channel → Opportunity → Confirmation → Risk → Execution →
Management → Learning. PostgreSQL (SQLite locally) is the only authority; workers are stateless between cycles.
Execution is permanently blocked at EXECUTION_BLOCKED_ANALYSIS_ONLY — no code path here submits broker orders.
"""
