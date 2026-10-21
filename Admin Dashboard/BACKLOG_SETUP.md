# Backlog dashboard setup

Three pieces go into AWS (region **us-west-1**, same as your other APIs): a DynamoDB table, a Lambda function, and an API Gateway REST API. Then you point `backlog.html` at the API and upload it next to your other admin pages.

## 1. Create the DynamoDB table

1. DynamoDB console → **Create table**.
2. Table name: `BacklogItems`
3. Partition key: `itemId` (String). No sort key.
4. Table settings → **Customize settings** → Capacity mode: **On-demand**. A backlog this size will cost pennies, if anything.
5. Create the table.

You don't need to add any data. The Lambda creates two counter records (`COUNTER#MAP` and `COUNTER#ADMIN`) the first time an item is added for each app. Leave those records alone, because they're how the next ID number is chosen. The dashboard hides them.

## 2. Create the Lambda function

1. Lambda console → **Create function** → Author from scratch.
2. Name: `manageBacklogItems`. Runtime: **Python 3.12**. Architecture: either.
3. Create the function, then replace the contents of `lambda_function.py` with `backlog_lambda.py` and click **Deploy**. The handler stays `lambda_function.lambda_handler`.
4. Optional: Configuration → Environment variables → `TABLE_NAME` = `BacklogItems`. This is only needed if you name the table something else.
5. Configuration → Permissions → click the execution role name. In IAM, choose **Add permissions → Create inline policy → JSON**, and paste the policy below (replace `ACCOUNT_ID` with your account number):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:Scan",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:us-west-1:ACCOUNT_ID:table/BacklogItems"
    }
  ]
}
```

Name it `BacklogItemsAccess` and save.

## 3. Create the API

1. API Gateway console → **Create API** → **REST API** → Build. Name: `backlog-api`. Endpoint type: Regional.
2. With `/` selected, **Create resource**. Resource name: `backlog`.
3. With `/backlog` selected, **Create method**:
   - Method type: **ANY**
   - Integration type: Lambda function, with **Lambda proxy integration turned on**
   - Lambda function: `manageBacklogItems`
4. With `/backlog` selected, **Create resource** again. Resource name: `{itemId}` (resource path `{itemId}`, including the braces).
5. With `/backlog/{itemId}` selected, create another **ANY** method, set up the same way as step 3.
6. **Deploy API** → New stage → Stage name: `prod`.
7. Copy the **Invoke URL**. It looks like `https://abc123xyz.execute-api.us-west-1.amazonaws.com/prod`.

The Lambda answers CORS preflight (OPTIONS) requests itself, so you don't need to click "Enable CORS".

**Quick check:** open `<Invoke URL>/backlog` in a browser. You should see `{"items": [], "count": 0}`.

## 4. Connect and upload the page

1. Open `backlog.html` and find this line in the `<script>` section:
   ```js
   const API_BASE_URL = 'https://YOUR-API-ID.execute-api.us-west-1.amazonaws.com/prod';
   ```
   Replace it with your Invoke URL. Do not add `/backlog` to the end.
2. Upload `backlog.html` wherever your other admin pages are hosted.
3. Optionally, add a link to it from `admin.html` or your other admin navigation.

## How the page works

- **IDs** are generated automatically when an item is added: `MAP-001`, `MAP-002`, `ADMIN-001`, and so on. The app can't be changed after creation because the ID depends on it.
- **Status** changes save as soon as you pick a new value in the table's dropdown.
- **Completed date** fills in automatically the first time an item is set to Completed. If the item is later moved back to another status, the date clears. If it's completed again, it gets a new date.
- **The default view is Open**, meaning everything except Completed and Not Planned. The status chips across the top double as filters: click Completed to review finished work, or All items to see everything. The page remembers the filters you last used in each browser.
- **Long descriptions and notes** show three lines in the table. Click the text to expand it, or open Edit to see and change everything.
- **Created and last-updated times** are stored for every item and shown in the Edit window.

## API reference

| Method | Path | Body | Result |
|---|---|---|---|
| GET | `/backlog` | | All items |
| POST | `/backlog` | `app` (MAP or ADMIN), `name` (required), `description`, `status`, `priority`, `notes` | The new item, with its ID |
| GET | `/backlog/{itemId}` | | One item |
| PUT | `/backlog/{itemId}` | Any of: `name`, `description`, `status`, `priority`, `notes` | The updated item |
| DELETE | `/backlog/{itemId}` | | `{"deleted": "MAP-001"}` |

Allowed status values are `Under Review`, `In Development`, `Completed`, `Delayed`, `Future Enhancement`, and `Not Planned`. Allowed priority values are `High`, `Medium`, and `Low`. New items default to Under Review and Medium.

## Optional: require an API key

Like your other endpoints, this API is open to anyone who has the URL. To restrict who can edit the backlog:

1. On `/backlog` and `/backlog/{itemId}`, use **Enable CORS** with `X-Api-Key` included in the allowed headers. This creates OPTIONS methods that don't require a key, which browsers need for preflight requests.
2. On each **ANY** method, open Method request → **API key required: true**.
3. Create an API key and a usage plan attached to the `prod` stage, then add the key to the plan.
4. Redeploy to `prod`.
5. In `backlog.html`, set `const API_KEY = 'your-key';`.

This keeps casual visitors out, but anyone who views the page source can see the key. If the admin pages ever get a real login (Cognito, for example), this API should move behind it too.
