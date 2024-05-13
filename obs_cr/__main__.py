import sys

def print_help():
    print("""\
Run one of the panels within python-cr.  Give an argument of `preview` or `control` and the respective arguments for that program.  Use `-h` to figure out what the arguments are:

    python obs-cr.pyz preview host:port password
    python obs-cr.pyz control host:port password
""")

def main():
    if len(sys.argv) < 2:
        print_help()
        sys.exit(1)

    cmd = sys.argv[1]
    del sys.argv[1]

    print(cmd)
    if cmd == 'control':
        from . import control
        control.main()

    elif cmd == 'preview':
        from . import preview
        try:
            import PIL
        except ImportError:
            print("You need pillow installed on your computer (e.g. package python-pillow)")
            print("Zipapps can't handle complied modules")
            exit(1)
        preview.main()
    else:
        print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
