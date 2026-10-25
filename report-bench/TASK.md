You are given data in the folder `data/`: one or more tables as CSV files, and a one-line title saying what the data is. Read and analyse the data, then make a data report about it: a web page that tells a reader what this data shows.

Deliver two files.

`facts.json`: the findings the page reports, each with the computation that produces it from the data.

How the findings are checked: every computation is run on the data, and each claim is compared with what its computation outputs, and with nothing else. A claim that says anything the output does not show counts as wrong, and one wrong finding scores the whole page 0. So every number, name and comparison in a claim must be readable from the output of its computation.

```json
[{"id": "west-returns-most",
  "claim": "Among regions with at least 100 orders, the West has the highest return rate: 19% of its 160 orders, against 13-14% in the East and North.",
  "series": [{"table": "orders.csv",
              "filter": "region.map(region.value_counts()) >= 100",
              "group": "region",
              "measure": "mean(returned == 'yes')"}]}]
```

- `id`: unique in the file, a few meaningful words.
- `claim`: the finding in one sentence, with its numbers.
- `series`: one computation on one table; two when the finding compares two tables grouped the same way.
  - `table`: the file's path under `data/`.
  - `filter`: the rows to keep, a pandas `DataFrame.query` expression (`engine="python"`). Leave it out to keep every row. Every condition the claim depends on (which rows, which years, how often something must appear) belongs here.
  - `group`: what splits the rows into the chart's categories (a bar, a point, a slice), a pandas `DataFrame.eval` expression: a column name or an expression such as `units > 100`, or a list of them to group by several at once, such as `["region", "product"]`. Leave it out for one overall value.
  - `measure`: the value of each group: `count` (rows), or `mean`, `median`, `sum`, `max` or `min` of a column or an expression, such as `mean(price)` or `mean(returned == 'yes')` (a share).

The output of one computation is a table with one row per group: the group's name (`a | b` when grouped by several), its value and how many rows it has. A claim that needs a number of its own needs a computation of its own, for example:
- "only four orders were for more than 690 units": `filter` `units > 690`, `measure` `count`;
- "the deepest discount was on an East-region desk": `group` `["region", "product"]`, `measure` `max(discount)`.

Run every computation yourself before you finish and check each claim against its output: `rows = df.query(filter, engine="python")`, group by the `group` expressions, aggregate the `measure`.

`index.html`: the page.
- Write all the text on the page in English.
- The page is opened offline. Put all CSS, scripts and data in the file; do not load anything from the network (no CDNs, web fonts, remote images or APIs).
- The page must open and show its content in a desktop browser (1440 px wide) without errors.

How you analyse the data, which tools you use and what the page looks like is up to you.
