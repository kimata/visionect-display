#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from cv2 import dnn_superres
from lxml import html
from urllib import request
from urllib.parse import urlparse
import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
import cv2
import datetime
import locale
import math
import numpy as np
import os
import pathlib
import logging


def get_font(config, font_type, size):
    return PIL.ImageFont.truetype(
        str(
            pathlib.Path(
                os.path.dirname(__file__), config["PATH"], config["MAP"][font_type]
            )
        ),
        size,
    )


def get_face_map(font_config):
    return {
        "date": {
            "month": get_font(font_config, "EN_COND_BOLD", 40),
            "day": get_font(font_config, "EN_BOLD", 150),
            "wday": get_font(font_config, "JP_BOLD", 100),
            "time": get_font(font_config, "EN_COND_BOLD", 28),
        },
        "temp": {
            "label": get_font(font_config, "JP_REGULAR", 24),
            "value": get_font(font_config, "EN_COND_BOLD", 86),
            "unit": get_font(font_config, "JP_REGULAR", 30),
        },
        "precip": {
            "label": get_font(font_config, "JP_REGULAR", 40),
            "value": get_font(font_config, "EN_COND_BOLD", 86),
            "unit": get_font(font_config, "JP_REGULAR", 30),
        },
        "weather": {
            "day": get_font(font_config, "EN_BOLD", 30),
            "value": get_font(font_config, "JP_REGULAR", 40),
        },
    }


def get_weather_yahoo(config):
    info = {
        "today": {},
        "tommorow": {},
    }
    data = request.urlopen(config["URL"])
    content = html.fromstring(data.read().decode("UTF-8"))

    for i, key in enumerate(info.keys()):
        parent_xpath = '//div[@class="forecastCity"]//td[{}]'.format(1 + i)

        text = content.xpath(parent_xpath + '//p[@class="date"]/text()')[0]
        info[key]["date"] = text

        img = content.xpath(parent_xpath + '//p[@class="pict"]/img')[0]
        info[key]["summary"] = img.attrib["alt"]
        info[key]["icon"] = img.attrib["src"]

        info[key]["temp"] = {}
        for item in ["high", "low"]:
            text = content.xpath(
                parent_xpath + '//li[@class="' + item + '"]/em/text()'
            )[0]
            info[key]["temp"][item] = text

        info[key]["precip"] = content.xpath(
            parent_xpath + '//tr[@class="precip"]/td/text()'
        )
        info[key]["precip"] = list(
            map(lambda s: s.replace("???", ""), info[key]["precip"])
        )

    return info


def draw_text(img, text, pos, font, align="left", color="#000"):
    draw = PIL.ImageDraw.Draw(img)

    if align == "center":
        pos = (pos[0] - font.getsize(text)[0] / 2, pos[1])
    elif align == "right":
        pos = (pos[0] - font.getsize(text)[0], pos[1])

    draw.text(pos, text, color, font, None, font.getsize(text)[1] * 0.4)

    return (pos[0] + font.getsize(text)[0], pos[1] + font.getsize(text)[1])


def get_image(info):
    tone = 32
    gamma = 0.24

    file_bytes = np.asarray(
        bytearray(request.urlopen(info["icon"]).read()), dtype=np.uint8
    )
    img = cv2.imdecode(file_bytes, cv2.IMREAD_UNCHANGED)

    # NOTE: ????????????????????????????????????
    img[img[..., -1] == 0] = [255, 255, 255, 0]
    img = img[:, :, :3]

    dump_path = str(
        pathlib.Path(
            os.path.dirname(__file__),
            "img",
            info["summary"] + "_" + os.path.basename(urlparse(info["icon"]).path),
        )
    )

    PIL.Image.fromarray(img).save(dump_path)

    h, w = img.shape[:2]

    # NOTE: ??????4???????????????????????????
    sr = dnn_superres.DnnSuperResImpl_create()

    model_path = str(pathlib.Path(os.path.dirname(__file__), "data", "ESPCN_x4.pb"))

    sr.readModel(model_path)
    sr.setModel("espcn", 4)
    img = sr.upsample(img)

    # NOTE: ???????????????
    tone_table = np.zeros((256, 1), dtype=np.uint8)
    for i in range(256):
        tone_table[i][0] = min(math.ceil(i / tone) * tone, 255)
    img = cv2.LUT(img, tone_table)

    # NOTE: ???????????????
    gamma_table = np.zeros((256, 1), dtype=np.uint8)
    for i in range(256):
        gamma_table[i][0] = 255 * (float(i) / 255) ** (1.0 / gamma)
    img = cv2.LUT(img, gamma_table)

    # NOTE: ???????????????????????????????????????
    img = cv2.resize(img, (int(w * 1.8), int(h * 1.8)), interpolation=cv2.INTER_CUBIC)

    # NOTE: ????????????????????????
    img = cv2.cvtColor(img, cv2.COLOR_RGB2RGBA)
    img[:, :, 3] = np.where(np.all(img == 255, axis=-1), 0, 255)

    return PIL.Image.fromarray(img).convert("LA")


def draw_icon(img, info, pos_x, pos_y, face_map):
    icon = get_image(info)
    img.paste(icon, (int(pos_x), pos_y))

    next_pos_y = pos_y
    next_pos_y += icon.size[1] * 1.1
    next_pos_y = draw_text(
        img,
        info["summary"],
        [pos_x + icon.size[0] / 2, next_pos_y],
        face_map["weather"]["value"],
        "center",
    )[1]


def draw_temp(img, info, pos_x, pos_y, face_map):
    face = face_map["temp"]

    for item in [("high", "??????"), ("low", "??????")]:
        label_pos_y = (
            pos_y + face["value"].getsize("0")[1] - face["label"].getsize(item[1])[1]
        )
        value_pos_x = (
            pos_x + face["label"].getsize(item[1])[0] + face["value"].getsize("-10")[0]
        )
        unit_pos_y = (
            pos_y + face["value"].getsize("0")[1] - face["unit"].getsize("???")[1]
        )
        unit_pos_x = value_pos_x + 5

        draw_text(img, item[1], [pos_x, label_pos_y], face["label"], color="#333")
        draw_text(
            img, info["temp"][item[0]], [value_pos_x, pos_y], face["value"], "right"
        )
        next_pos_x = draw_text(img, "???", [unit_pos_x, unit_pos_y], face["unit"])[0]

        pos_y += int(face["value"].getsize("0")[1] * 1.4)

    return next_pos_x


def draw_precip(img, info, pos_x, pos_y, face_map):
    face = face_map["temp"]

    for i, label in enumerate(["??????", "??????", "??????", "???"]):
        if i == 0:
            continue

        label_pos_y = (
            pos_y + face["value"].getsize("0")[1] - face["label"].getsize("??????")[1]
        )
        value_pos_x = (
            pos_x + face["label"].getsize("?????????")[0] + face["value"].getsize("---")[0]
        )
        unit_pos_y = (
            pos_y + face["value"].getsize("0")[1] - face["unit"].getsize("%")[1]
        )
        unit_pos_x = value_pos_x + 5

        draw_text(img, label, [pos_x, label_pos_y], face["label"], color="#333")
        draw_text(img, info["precip"][i], [value_pos_x, pos_y], face["value"], "right")
        next_pos_x = draw_text(img, "%", [unit_pos_x, unit_pos_y], face["unit"])[0]

        pos_y += int(face["value"].getsize("0")[1] * 1.2)

    return next_pos_x


def draw_weather(img, label, info, pos_x, pos_y, face_map):
    next_pos_y = draw_text(
        img, label, [pos_x, pos_y], face_map["weather"]["day"], color="#999"
    )[1]
    draw_icon(img, info, pos_x, next_pos_y, face_map)
    next_pos_x = draw_temp(img, info, pos_x + 265, pos_y + 45, face_map)
    next_pos_x = draw_precip(img, info, next_pos_x + 30, pos_y + 45, face_map)

    return next_pos_x


def draw_date(img, pos_x, pos_y, face_map):
    face = face_map["date"]

    now = datetime.datetime.now()

    pos_x = pos_x + face["day"].getsize("31")[0] / 2
    day_pos_y = pos_y + int(face["month"].getsize("D")[1] * 1.2)
    wday_pos_y = day_pos_y + int(face["day"].getsize("D")[1] * 1.2)

    locale.setlocale(locale.LC_TIME, "en_US.UTF-8")
    draw_text(img, now.strftime("%B"), [pos_x, pos_y], face["month"], "center", "#666")
    draw_text(img, str(now.day), [pos_x, day_pos_y], face["day"], "center", "#666")
    locale.setlocale(locale.LC_TIME, "ja_JP.UTF-8")
    next_pos_x = draw_text(
        img, now.strftime("%a"), [pos_x, wday_pos_y], face["wday"], "center", "#666"
    )[0]

    return next_pos_x


def draw_time(img, pos_x, pos_y, face_map):
    face = face_map["date"]

    now = datetime.datetime.now()

    locale.setlocale(locale.LC_TIME, "en_US.UTF-8")
    next_pos_x = draw_text(
        img, now.strftime("%H:%M"), [pos_x, pos_y], face["time"], "right", "#666"
    )

    return next_pos_x


def draw_panel_weather(img, config, font_config, weather_info):
    face_map = get_face_map(font_config)
    draw_date(img, 5, 15, face_map)
    draw_time(img, config["WIDTH"] - 5, 15, face_map)
    next_pos_x = draw_weather(img, "Today", weather_info["today"], 210, 15, face_map)
    next_pos_x = draw_weather(
        img, "Tommorow", weather_info["tommorow"], next_pos_x + 30, 15, face_map
    )


def create_weather_panel(config, font_config):
    logging.info("draw weather panel")

    weather_info = get_weather_yahoo(config["DATA"]["YAHOO"])
    img = PIL.Image.new("RGBA", (config["WIDTH"], config["HEIGHT"]), (255, 255, 255, 0))

    draw_panel_weather(img, config, font_config, weather_info)

    return img
