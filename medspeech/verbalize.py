"""Deterministic, documented TTS input rendering; not an STT correction rule."""
import re

DIGITS="영일이삼사오육칠팔구"


def sino(value):
    if "." in value:
        whole,fraction=value.split(".")
        return sino(whole)+" 점 "+" ".join(DIGITS[int(x)] for x in fraction)
    number=int(value)
    if number==0: return "영"
    if number>=10000: raise ValueError("TTS number renderer supports 0..9999")
    output=""
    for power,unit in [(1000,"천"),(100,"백"),(10,"십"),(1,"")]:
        digit,number=divmod(number,power)
        if digit: output+=("" if digit==1 and power>1 else DIGITS[digit])+unit
    return output


def spoken_text(text):
    for source,target in [("SpO2","산소 포화도"),("MRI","엠알아이"),("LDL","엘디엘"),("CT","씨티"),("Cr","씨알"),
                          ("mg/dL","밀리그램 퍼 데시리터"),("mmHg","밀리미터 머큐리"),("mcg","마이크로그램"),("mg","밀리그램"),("%","퍼센트")]:
        text=text.replace(source,target)
    return re.sub(r"\d+(?:\.\d+)?",lambda m:sino(m[0]),text)
