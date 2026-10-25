You are given data in the folder `data/`: one or more tables as CSV files, and a one-line title saying what the data is. Read and analyse the data, then make a data report about it: a web page that tells a reader what this data shows.

Deliver two files.

`facts.json`: the findings the page reports, each with the pandas code that computes it from the data.

```json
[{"id": "west-returns-most",
  "claim": "Among regions with at least 100 orders, the West has the highest return rate, 19%, against 14% in the East and 13% in the North.",
  "tables": {"orders": "data/orders.csv"},
  "code": "orders[orders.region.map(orders.region.value_counts()) >= 100].groupby('region').returned.apply(lambda s: (s == 'yes').mean())"}]
```

- `id`: unique in the file, a few meaningful words.
- `claim`: the finding in one sentence, with its numbers.
- `tables`: the files the code reads, each a variable name and the file's path from this folder, such as `data/orders.csv`; every file is read with `pd.read_csv(path)`.
- `code`: one Python expression over those variables, with `pd` (pandas) and `np` (numpy) available, such as `(orders.units > 690).sum()` or `orders.groupby(['region', 'product']).discount.max()`.

How the findings are checked: every `code` is evaluated as written, its value is printed the way pandas prints it, and each claim is compared with that printout and nothing else. A claim that says anything the printout does not show counts as wrong, and one wrong finding scores the whole page 0. So every number, name and comparison in a claim must be readable from the printout of its code, and computed by that code from the tables: code that writes a finding's numbers itself, such as a string or a Series of typed-in values, counts as wrong. Before you finish, evaluate every fact the same way from this folder: read its `tables` with `pd.read_csv`, evaluate its `code`, print the value, and read the printout against the claim.

`index.html`: the page.
- Write all the text on the page in English.
- The page is opened offline. Put all CSS, scripts and data in the file; do not load anything from the network (no CDNs, web fonts, remote images or APIs).
- The page must open and show its content in a desktop browser (1440 px wide) without errors.

How you analyse the data, which tools you use and what the page looks like is up to you.
