@echo off
rem Launch the agent in bridge input mode: the Godot
rem panel input box drives it instead of the terminal.
cd /d "%~dp0"
set AGENT_INPUT_MODE=bridge
py -m agent.godot_agent
