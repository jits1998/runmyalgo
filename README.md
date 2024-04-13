# Steps to run:

1. Checkout project
2. create venv
3. select venv
4. run bash init.py
5. create a json file with a short code containing the following:

```json
{
  "broker": "zerodha",
  "clientID": "",
  "appKey": "",
  "appSecret": "",
  "multiple": "1",
  "algo_type" : "TestAlgo"
}
```

6. run flask app
