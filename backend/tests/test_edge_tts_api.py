import inspect
try:
    import edge_tts
    print(inspect.signature(edge_tts.Communicate.__init__))
except Exception as e:
    print(e)
