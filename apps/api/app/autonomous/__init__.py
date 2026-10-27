"""Autonomous Trading Engine: a persistent, closed-bar state machine over the existing intelligence engines.

Market Data → Intelligence → Scanner → Structure → Channel → Opportunity → Confirmation → Risk → Execution →
Management → Learning. PostgreSQL (SQLite locally) is the only authority; workers are stateless between cycles.
In ANALYSIS_ONLY or SHADOW, strategy execution stops at EXECUTION_BLOCKED_ANALYSIS_ONLY. AI Market Outlook (Mode 2) and live autonomous strategy paths submit broker orders when system mode and account policy allow.
"""
