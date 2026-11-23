# AI Crypto News & Macro Intelligence by Sali

Magyar nyelvű Telegram-riasztó teljes kriptopiaci és kiemelt BTC-hírekhez,
valamint makro- és szabályozói közleményekhez.

## Telepítés

1. Telepíts Python 3.10 vagy újabb verziót.
2. Csomagold ki a projektet.
3. Telepítsd a függőségeket:
   `pip install -r requirements.txt`
4. Másold az `.env.example` fájlt `.env` néven.
5. Töltsd ki a Telegram bot tokenjét, chat ID-t és Groq API-kulcsot.
6. Opcionálisan add meg a Finnhub API-kulcsot a makronaptár tényadat-riasztásaihoz.
7. Indítás:
   `python sali_crypto_alert_bot.py`

## Mit figyel?

- Kriptós RSS-hírforrások: CoinDesk, Cointelegraph, Bitcoin Magazine,
  Blockworks, Decrypt, The Block.
- Hivatalos makro- és szabályozói közlemények: Federal Reserve, BLS,
  BEA, U.S. Treasury, SEC.
- Finnhub gazdasági naptár: az amerikai eseményeknél az `actual` érték
  megjelenését figyeli (API-kulcs szükséges).

## Fontos működési korlát

A bot a források frissülésétől függően, a beállított ciklusban ellenőriz.
A `POLL_SECONDS=20` azt jelenti, hogy legfeljebb körülbelül 20 másodpercenként
indít új ellenőrzési kört, de a kiadó RSS/API frissítése késhet. Ez nem
garantál milliszekundumos vagy minden forrásnál azonos pillanatú riasztást.
A valóban alacsony késleltetésű hírszolgáltatáshoz fizetős, push/webhookos
hír- vagy piaci adatforrás szükséges lehet.

Az első induláskor csak feedenként a legutóbbi két hírt dolgozza fel,
hogy ne küldje ki a teljes archívumot. A későbbi új híreket azonnal továbbítja.
A már elküldött híreket helyi JSON-állományban tárolja, így újraindítás után
sem küldi ki őket ismét.

## Biztonság

- A `.env` fájlt soha ne töltsd fel GitHubra.
- Add hozzá a `.env`-t a `.gitignore` fájlhoz.
- A tokeneket ne írd bele közvetlenül a Python-kódba.
- A bot nem kereskedési jeladó: a hírbesorolás AI-alapú értelmezés, nem
  garantált árfolyam-előrejelzés.
