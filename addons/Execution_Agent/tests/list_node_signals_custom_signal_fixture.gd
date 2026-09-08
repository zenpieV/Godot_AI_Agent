extends Node

# Test fixture for the list_node_signals headless
# harness: a real scripted node declaring one custom
# signal, so the harness can prove that script-defined
# signals are discovered through Node.get_signal_list().

signal health_changed(new_health: int)
