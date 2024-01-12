#!/usr/bin/env python3

import sys

import pymongo



def main():
    client = pymongo.MongoClient("mongodb://localhost:27017/")
    client.drop_database("seo")



if __name__ == "__main__":
    sys.exit(main())
