The folder `data/` holds the data behind a published data story, "The Unlikely Odds of Making it Big": https://pudding.cool/2017/01/making-it-big/
The files: data/web_data.csv, data/web_venues.csv, data/web_made.csv

Write down the story's findings that this data reproduces.

1. Read the story on the web. web_fetch returns the page as the server sends it. web_view opens it in a browser and scrolls it like a reader, so it also gets text drawn by scripts, chart labels and the text of scrolling steps: use it when web_fetch returns little of the story, and to read what the charts label. Follow links to the story's methods or data notes when they say how a number was computed.
2. List every finding the authors draw from data: each number, comparison, ranking, share, trend or pattern the text states or a chart labels. A description of the data itself is not a finding: how many records, people, items, categories or sources it has, and how it was collected. When a chart states the same thing for each of its items (the top three for each phrase, the share for each year), that is one finding, written as one fact whose code computes it for every item at once.
3. Write each finding the files in data/ can reproduce as a fact in `facts.json`:

```json
[{"id": "women-front-shorter",
  "source": "On average, the pockets in women's jeans are 48% shorter and 6.5% narrower than men's pockets.",
  "claim": "Women's front pockets average 14.3 cm of maximum height against 23.1 cm for men.",
  "tables": {"m": "data/measurements.csv"},
  "code": "m.groupby('menWomen').maxHeightFront.mean()"}]
```

- `id`: unique in the file, a few meaningful words.
- `source`: the story's own words for this finding, quoted exactly, from its text or a chart label.
- `claim`: the finding in one sentence, with the numbers the code prints, and nothing the printout does not show: the story's own wording and numbers belong in `source`, not in the claim.
- `tables`: the files the code reads, each a variable name and the file's path from this folder, such as `data/orders.csv`; every file is read with `pd.read_csv(path)`.
- `code`: one Python expression over those variables, with `pd` (pandas) and `np` (numpy) available: the plain pandas computation whose printout shows the finding, such as a filter, a group-by, a count, a share or a sort. Do not assemble the result into a hand-made Series or dict.

Evaluate every fact from this folder the way it will be checked: read its `tables` with `pd.read_csv`, evaluate its `code`, print the value the way pandas prints it, and read the printout against the claim and the source. Every number, name and comparison in the claim must be in the printout, computed from the tables: code that writes a number itself, such as a string or a Series of typed-in values, does not count. The printout must agree with the story's numbers, up to rounding. Use the story's own definitions and filters, from its text or methods: a term means the same in every fact (if making it past the rookie contract is more than two seasons in one fact, it is more than two seasons in all of them), and a range, threshold or subset is one the story uses, never one chosen to make a number come out right. If the story's number only comes out under a definition or filter the story does not use, the finding is not reproduced. If after a fair try the data does not give the story's number (it needs other data, a different period, or the numbers differ beyond rounding), leave the finding out of facts.json.

4. Write `skipped.json`: every finding you left out, as [{"source": "the story's words", "why": "..."}].

Deliver both files, even when the data reproduces none of the story's findings: then `facts.json` is `[]`.
