import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
from netmiko import ConnectHandler


CMD = "show ip interface brief"  # 接口IP + status/protocol 最常用


def load_devices(path="devices.csv"):
    devices = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            devices.append({
                "device_type": "cisco_ios",  # IOS/IOS-XE 用这个；NX-OS 用 cisco_nxos
                "host": row["host"].strip(),
                "username": row["username"].strip(),
                "password": row["password"].strip(),
                "secret": (row.get("secret") or "").strip(),
                "port": int(row.get("port") or 22),
                "name": row.get("name", row["host"]).strip(),
            })
    return devices


def run_show(dev):
    result_rows = []
    try:
        with ConnectHandler(**{k: v for k, v in dev.items() if k in ["device_type", "host", "username", "password", "port"]}) as conn:
            if dev.get("secret"):
                conn.enable()

            # use_textfsm=True 会返回结构化列表（需要 ntc-templates）
            output = conn.send_command(CMD, use_textfsm=True)

            if isinstance(output, list):
                # 结构化结果：字段名可能因模板略有差异，这里做兼容
                for item in output:
                    result_rows.append({
                        "device": dev["name"],
                        "host": dev["host"],
                        "interface": item.get("intf") or item.get("interface"),
                        "ip_address": item.get("ipaddr") or item.get("ip_address"),
                        "status": item.get("status"),
                        "protocol": item.get("proto") or item.get("protocol"),
                        "method": item.get("method"),
                    })
            else:
                # 没有 textfsm 模板时：把原始输出也保留下来，至少不丢数据
                result_rows.append({
                    "device": dev["name"],
                    "host": dev["host"],
                    "interface": "",
                    "ip_address": "",
                    "status": "RAW_OUTPUT",
                    "protocol": "",
                    "method": "",
                    "raw": str(output),
                })

        return result_rows, None

    except Exception as e:
        return [], f"{dev['name']}({dev['host']}): {e}"


def main():
    devices = load_devices("devices.csv")

    all_rows = []
    errors = []

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(run_show, d) for d in devices]
        for fu in as_completed(futures):
            rows, err = fu.result()
            all_rows.extend(rows)
            if err:
                errors.append(err)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    df = pd.DataFrame(all_rows)

    # 输出
    csv_out = f"intf_status_{ts}.csv"
    xlsx_out = f"intf_status_{ts}.xlsx"
    df.to_csv(csv_out, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_out, index=False)

    print(f"Saved: {csv_out}, {xlsx_out}")
    if errors:
        print("\nErrors:")
        for e in errors:
            print(" -", e)


if __name__ == "__main__":
    main()