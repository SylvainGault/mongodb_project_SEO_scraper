#!/usr/bin/env python3

import datetime
import sys

import pymongo



def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} url scope")
        return 1

    url = sys.argv[1]
    scope = sys.argv[2]


    client = pymongo.MongoClient("mongodb://localhost:27017/")
    db = client["seo"]
    coll_urls = db["urls"]
    coll_logs = db["logs"]

    now = datetime.datetime.now()
    doc = {
            "url": url,
            "scope": scope,
            "status": "pending",
            "added_at": now,
    }
    # FIXME: possible race condition
    res = coll_urls.insert_one(doc)
    print(f"URL inserted as id {res.inserted_id}")

    log = {
        "date": now,
        "msg": "Added url {url} with scope {scope}",
        "url": url,
        "scope": scope
    }
    coll_logs.insert_one(log)



if __name__ == "__main__":
    sys.exit(main())
