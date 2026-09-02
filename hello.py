import sys, os
msg = "HELLO-RAN " + sys.version.replace("\n", " ")
print(msg)
try:
    with open(os.path.join(os.path.dirname(sys.executable), "hello_ran.txt"), "w") as f:
        f.write(msg)
except Exception as e:
    print("logfail", e)
