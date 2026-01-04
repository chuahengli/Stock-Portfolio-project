import moomoo_api

def main():
    data = moomoo_api.main()
    # data = {"account_list": ..., "account_info": ..., "positions": ..., "cashflow": ..., "historical_orders": ...}
    print(data["positions"])
    return 0

if __name__ == "__main__":
    main()

