#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import influxdb_client

import datetime
import dateutil.parser

INFLUXDB_QUERY = """
SELECT mean("{param}") FROM "sensor.{sensor_type}" WHERE ("hostname" = \'{hostname}\') AND time >= now() - {period} GROUP BY time(1m) fill(previous) ORDER by time asc
"""


def fetch_data(config, sensor_type, hostname, param, period="60h"):
    client = influxdb_client.InfluxDBClient(
        url=config["URL"], token=config["TOKEN"], org=config["ORG"]
    )

    query_api = client.query_api()

    query = """from(bucket: "{bucket}")
        |> range(start: -{period})
        |> filter(fn:(r) => r._measurement == "sensor.{sensor_type}")
        |> filter(fn: (r) => r.hostname == "{hostname}")
        |> filter(fn: (r) => r["_field"] == "{param}")
        |> aggregateWindow(every: 3m, fn: mean, createEmpty: false)
        |> exponentialMovingAverage(n: 3)
    """

    table_list = query_api.query(
        query=query.format(
            bucket=config["BUCKET"],
            sensor_type=sensor_type,
            hostname=hostname,
            param=param,
            period=period,
        )
    )

    data = []
    time = []
    localtime_offset = datetime.timedelta(hours=9)

    if len(table_list) != 0:
        for record in table_list[0].records:
            data.append(record.get_value())
            time.append(record.get_time() + localtime_offset)

    return {"value": data, "time": time, "valid": len(time) != 0}
