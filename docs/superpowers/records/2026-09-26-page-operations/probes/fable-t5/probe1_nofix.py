import contextlib, runpy, sys
sys.path.insert(0, "D:/Coding/8848 Lab/pdf-ai")
import engine.operations as ops
ops.at_rotation_zero = lambda page: contextlib.nullcontext()  # neutralise the fix in-process
runpy.run_path("C:/Users/Anup/AppData/Local/Temp/claude/D--Coding-8848-Lab-Himalaya/751b8304-03da-47cb-9004-bad558dd3cf1/scratchpad/fable-t5/probe1_matrix.py", run_name="__main__")
