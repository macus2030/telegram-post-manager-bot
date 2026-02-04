
import py_compile
import sys
import traceback

try:
    py_compile.compile('d:\\Project\\TG_BOT\\handlers\\manager.py', doraise=True)
    print("Success!")
except py_compile.PyCompileError as e:
    print(f"Error: {e}")
    # Often e.msg contains details, or we print traceback
    traceback.print_exc()
except Exception as e:
    print(f"General Error: {e}")
    traceback.print_exc()
