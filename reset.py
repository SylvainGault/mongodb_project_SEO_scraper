#!/usr/bin/env python3

import sys

import pymongo



def main():
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    client.drop_database("seo")

    db = client["seo"]
    coll_urls = db["urls"]
    coll_docs = db["docs"]
    coll_logs = db["logs"]

    coll_logs.create_index([("date", 1)])
    coll_docs.create_index([("url", 1), ("scope", 1), ("fetch_date", 1)])
    coll_urls.create_index([("status", "hashed")])
    coll_urls.create_index([("url", 1), ("scope", 1)])



if __name__ == "__main__":
    sys.exit(main())
