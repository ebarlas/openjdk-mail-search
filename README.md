## OpenJDK Mail Search

![Duke Mascot](duke.png)

OpenJDK Mail Search is a collection of tools for locating, indexing, and searching OpenJDK mailing list records.

The goal is to produce a website with a search interface that provides access to the entire mailing list
history for targeted lists.

Searches are based on (1) exact-match for mail author name and email and (2) phrase-query for mail subject and body.

This results in fast, predictable search outcomes tailored for simple code-related queries.

https://openjdk.barlasgarden.com

Thank you to [@bowbahdoe](https://github.com/bowbahdoe) for the Duke art and for other collaborations on this project. 

## Indexing Pipeline

Indexing functionality resides in the `indexer.py` module. The module contain an `index` function
that accepts mailing list record fields and returns a list of terms.

There are 4 mailing list record fields that are indexed: (1) author, (2) email, (3) subject, and (4) body.

They each pass through this indexing pipeline and contribute to the final terms result.

### 1. Record Filtering

Mail records that match a stop-function are not indexed at all.

### 2. Line Filtering

Mail body lines that match stop-line exclusion rules are removed from the input prior to tokenization.

For example, quoted text lines `\W*>` are not indexed.

### 3. Tokenization

The input is split on whitespace and converted to lowercase.

* `Project Panama` → `project`, `panama`

### 4. Pre-Filtering

Prior to normalization, tokens longer than 100 characters and tokens with stop-prefixes (e.g. `https://`) are excluded.

### 5. Normalization

Tokens are stripped of non-word characters defined by `[^\w+#]`.

* `snake_case` → `snake_case` (underscore kept)
* `C++` → `c++` (plus kept)
* `C#` → `c#` (hash kept)
* `SSL-socket` → `sslsocket` (hyphen removed)

### 6. Post-Filtering

Stop words are removed from the normalized tokens.

```
a, an, and, are, as, at, be, but, by, for, if, in, into, is, it, no,
not, of, on, or, such, that, the, their, then, there, these, they, this, to,
was, will, with
```

* `... This, is, an, outrage ...` → `... outrage ...` 

### 7. Word N-grams

Tokens are arranged into terms, the final product of this pipeline.

Short, contiguous sequences of tokens are added as terms.

A word n-gram length of 3 is used for the mail body, and an n-gram length of 5 is used for the author, email, and subject.

Additionally, author, email, and subject all include the full normalized token list as a single phrase term.

* `... data, oriented, programming ...` →
```
[data]
[data, oriented]
[data, oriented, programming]
[oriented]
[oriented, programming]
[programming]
```

### 8. Term Filtering

High-frequency terms, such as `[have]`, `[should]`, and `[i, think]` are removed.

### 9. Code-Aware Segmentation

This stage runs after pre-filtering. It performs additional tokenization on words that contain structural delimiters.

Raw tokens are split on `/`, `.`, `=`, and `::`.

All contiguous segment combinations are normalized, filtered, joined, and added as terms.
This makes strings like `java.util.concurrent` and `org/example/Main` discoverable in multiple ways.

A word n-gram length of 10 is used for code segments.

* `java.util.concurrent` →
```
[java]
[javautil]
[javautilconcurrent]
[util]
[utilconcurrent]
[concurrent]
```

### Conventions and Edge Cases

* Email is used as author if the author field doesn't exist in the mail record
* Git and Mercurial changeset emails are not indexed
* Quoted lines starting with `>` are not indexed
* Word n-gram length of 3 for mail body
* Word n-gram length of 5 for mail subject
* Word n-gram length of 10 for code segments
* Maximum token size of 100
* Maximum of 100 code segment terms
* Maximum of 2,500 terms per indexed mail record

## Project

These are the various tools in this repo:
* `seed.py` - CLI tool for seeding mailing list index
* `server.py` - AWS Lambda API server for processing mailing list queries
* `updater.py` - AWS Lambda scheduled job for continuously updating indexes
* `index.html` - static website with mailing list search interface

The website is deployed using a simple AWS stack:
* DynamoDB - indexes and metadata stored here
* S3 - static website content, including the search page
* CloudFront - website gateway with API lambda function attached
* Lambda - compute for API server and scheduled job

## DynamoDB

Attribute definitions:
* `term` string - search term, e.g. `SSLSocket`
* `date` string - fixed-width ISO-8601 date in UTC, e.g. `2025-08-24T20:07:24Z`
* `list` string - mailing list name, e.g. `net-dev`
* `month` string - mailing list month, e.g. `2025-August`
* `id` string - mail ID, e.g. `027714`
* `author` string - author name, e.g. `Peter Parker`
* `authorkey` string - normalized author name, e.g. `peterparker`
* `email` string - author email, e.g. `peter.parker@marvel.com`
* `emailkey` string - normalized author email, e.g. `peterparkermarvelcom`

Tables:
* `openjdk-mail-terms`
  * [PK] `p` (short for `list_term` partition key)
    * Slash-delimited composition of `list`, `term`
    * e.g. `net-dev/SSLSocket`
  * [SK] `s` (short for `date_month_id` sort key)
    * Slash-delimited composition of `date`, `month`, `id`
    * e.g. `2025-08-24T20:07:24Z/2025-August/027714`
  * [GSI] `term_date`
    * [PK] `t` (short for `term` partition key)
    * [SK] `d` (short for `date` sort key
* `openjdk-mail-records`
  * [PK] `list`
  * [SK] `month_id`
    * Slash-delimited composition of `month`, `id`
    * e.g. `2025-August/027714`
  * [LSI] `list_date`
    * [PK] `list`
    * [SK] `date`
  * [LSI] `list_authorkey_date`
    * [PK] `list`
    * [SK] `authorkey_date`
      * Slash-delimited composition of `authorkey`, `date`
      * e.g. `peterparker/2025-08-24T20:07:24Z`
  * [LSI] `list_emailkey_date`
    * [PK] `list`
    * [SK] `emailkey_date`
      * Slash-delimited composition of `emailkey`, `date`
      * e.g. `peterparkermarvelcom/2025-08-24T20:07:24Z`
  * [GSI] `month_date`
    * [PK] `month`
    * [SK] `date`
  * [GSI] `authorkey_date`
    * [PK] `authorkey`
    * [SK] `date`
  * [GSI] `emailkey_date`
    * [PK] `emailkey`
    * [SK] `date`
  * [GSI] `datekey_date`
    * [PK] `datekey`
    * [SK] `date`
* `openjdk-mail-checkpoints`
  * [PK] `list`
* `openjdk-mail-status`
  * [PK] `pk`


## Query API

Full request/response details, schemas, and examples are in [openapi.yaml](openapi.yaml) (OpenAPI 3.0).

* Search mail in a list
  * `GET /lists/{list}/mail/search?q={query}&order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`
* Get latest mail for a list
  * `GET /lists/{list}/mail?order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`
* Get mail for a list by author name
  * `GET /lists/{list}/mail/byauthor?author={author}&order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`
* Get mail for a list by author email
  * `GET /lists/{list}/mail/byemail?email={email}&order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`
* Search mail across all lists
  * `GET /mail/search?q={query}&order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`
* Get mail across all lists by author name
  * `GET /mail/byauthor?author={author}&order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`
* Get mail across all lists by author email
  * `GET /mail/byemail?email={email}&order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`
* Get mail across all lists
  * `GET /mail?order={asc|desc}&limit={limit}&cursor={cursor}&from={from}&to={to}`