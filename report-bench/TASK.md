You are given data in the folder `data/`: one or more tables as CSV files, and a one-line title saying what the data is. Read and analyse the data, then make a data report about it: a web page that tells a reader what this data shows.

Deliver two files.

`facts.json`: the findings the page reports, each with the computation that produces it from the data. The computation is run again to check the page, so it must reproduce what the page says.

```json
[{"id": "books-female-animals",
  "claim": "Among animals that appear in at least 10 books, only birds (63% she) and ducks (57% she) are more often female than male.",
  "series": [{"table": "kids-book-animals.csv",
              "filter": "pronoun in ['he/him', 'she/her'] and title.groupby(animal).transform('nunique') >= 10",
              "group": "animal",
              "measure": "mean(pronoun == 'she/her')"}]}]
```

- `id`: unique in the file, a few meaningful words.
- `claim`: the finding in one sentence, with its numbers.
- `series`: one computation on one table; two when the finding compares two tables grouped the same way.
  - `table`: the file's path under `data/`.
  - `filter`: the rows to keep, a pandas `DataFrame.query` expression (`engine="python"`). Leave it out to keep every row. Every condition the claim depends on (which rows, which years, how often something must appear) belongs here.
  - `group`: what splits the rows into the chart's categories (a bar, a point, a slice), a pandas `DataFrame.eval` expression: a column name or an expression such as `total_seasons > 2`. Leave it out for one overall value.
  - `measure`: the value of each group: `count` (rows), or `mean`, `median`, `sum`, `max` or `min` of a column or an expression, such as `mean(price)` or `mean(pronoun == 'he')` (a share).

`index.html`: the page.
- Write all the text on the page in English.
- The page is opened offline. Put all CSS, scripts and data in the file; do not load anything from the network (no CDNs, web fonts, remote images or APIs).
- The page must open and show its content in a desktop browser (1440 px wide) without errors.
- Mark where the page states each fact with `data-ref`, its value the fact's `id`: wrap the sentence that states it in `<span data-ref="...">`, and put `data-ref` on the outermost element of the chart that shows it (several ids separated by spaces when one chart shows several facts). Every statement about the data (a number, a comparison, a most or least, a trend) belongs in a sentence marked with the fact that computes it. Background, history, quotes and method notes need no mark.

How you analyse the data, which tools you use, how charts are drawn (SVG or canvas) and what the page looks like is up to you.
