import argparse
from .auth import login
from .upload import upload_file
from .download import download_file
from .list import list_files, file_info
from .session import load_token, save_token


def main():
    parser = argparse.ArgumentParser(description="Bluetap Distributed Storage Client")

    parser.add_argument("--gateway", default="127.0.0.1:50052", help="Gateway address")

    sub = parser.add_subparsers(dest="command")

    # login
    login_cmd = sub.add_parser("login")
    login_cmd.add_argument("--user", required=True)
    login_cmd.add_argument("--passw", required=True)

    # upload
    upload_cmd = sub.add_parser("upload")
    upload_cmd.add_argument("--file", required=True)
    upload_cmd.add_argument("--chunk-size", type=int, default=512 * 1024)
    upload_cmd.add_argument("--replication", type=int, default=1)

    # download
    download_cmd = sub.add_parser("download")
    download_cmd.add_argument("--filename", required=True)

    # list files
    list_cmd = sub.add_parser("list-files")

    # file info
    info_cmd = sub.add_parser("file-info")
    info_cmd.add_argument("--filename", required=True)

    args = parser.parse_args()

    if args.command == "login":
        token = login(args.gateway, args.user, args.passw)
        save_token(token)
        print("Logged in. Token saved:", token)

    else:
        # all other commands need token
        token = load_token()
        if not token:
            print("ERROR: Not logged in. Run: python -m client.cli login --user U --passw P")
            return

        if args.command == "upload":
            upload_file(args.gateway, token, args.file, args.chunk_size, args.replication)

        elif args.command == "download":
            download_file(args.gateway, token, args.filename)

        elif args.command == "list-files":
            list_files(args.gateway, token)

        elif args.command == "file-info":
            file_info(args.gateway, token, args.filename)

        else:
            print("Unknown command")


if __name__ == "__main__":
    main()
