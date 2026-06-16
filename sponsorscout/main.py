import sys

def main():
    from sponsorscout.ui.app import main as app_main
    app_main(start_minimized="--background" in sys.argv)

if __name__ == "__main__":
    main()
