# Data audit

Run `audit-20260906T164448Z-4c524298` · protocol 2.0.0 · audited 2026-09-06T16:46:15.369160+00:00

This audit reports what the downloaded bytes actually contain. It modifies nothing. Every cleaning decision made afterwards is justified against the evidence here.

## Headline counts

| quantity | value |
| --- | --- |
| recipes: raw rows | 231637 |
| recipes: unique ids | 231637 |
| recipes: exact duplicate rows | 0 |
| recipes: conflicting ids | 0 |
| recipes: submitted date range | 1999-08-06 00:00:00 .. 2018-12-04 00:00:00 |
| recipes: non-positive minutes | 1094 |
| recipes: missing/blank description | 2.1508 |
| interactions: raw rows | 1132367 |
| interactions: unique users | 226570 |
| interactions: unique recipe ids | 231637 |
| interactions: exact duplicate rows | 0 |
| interactions: repeated user-recipe pairs | 0 |
| interactions: date range | 2000-01-25 00:00:00 .. 2018-12-20 00:00:00 |
| interactions: rating 0 (unknown) | 60847 |
| interactions: positive (4-5) | 1003724 |
| interactions: observed non-positive (1-3) | 67796 |
| interactions: orphan recipe joins | 0 |
| interactions: dated before submission | 1246 |
| recipe id is a unique key | True |

## Temporal coverage of the locked windows

Workable: **True**

| stage | history_end_exclusive | label_start | label_end_inclusive | n_history_events | n_label_events |
| --- | --- | --- | --- | --- | --- |
| validation | 2017-01-01 | 2017-01-01 | 2017-12-31 | 1084658 | 27062 |
| final | 2018-01-01 | 2018-01-01 | 2018-12-20 | 1111720 | 20647 |

## recipes — recipes by submitted year

| year | n_recipes |
| --- | --- |
| 1999 | 2054 |
| 2000 | 1038 |
| 2001 | 4682 |
| 2002 | 20056 |
| 2003 | 18000 |
| 2004 | 16601 |
| 2005 | 23865 |
| 2006 | 27260 |
| 2007 | 34299 |
| 2008 | 30745 |
| 2009 | 22547 |
| 2010 | 11902 |
| 2011 | 7573 |
| 2012 | 5187 |
| 2013 | 3792 |
| 2014 | 1049 |
| 2015 | 306 |
| 2016 | 204 |
| 2017 | 288 |
| 2018 | 189 |

## recipes — recipe minutes bands

| band | n_recipes |
| --- | --- |
| G1_0_15 | 42828 |
| G2_15_30 | 55131 |
| G3_30_60 | 70077 |
| G4_60_plus | 62507 |
| unassigned_invalid_minutes | 1094 |

## recipes — recipe minutes histogram

| minutes_bin | n_recipes |
| --- | --- |
| (0.0, 5.0] | 13635 |
| (5.0, 10.0] | 14127 |
| (10.0, 15.0] | 15066 |
| (15.0, 20.0] | 17924 |
| (20.0, 30.0] | 37207 |
| (30.0, 45.0] | 41486 |
| (45.0, 60.0] | 28591 |
| (60.0, 90.0] | 29071 |
| (90.0, 120.0] | 7612 |
| (120.0, 180.0] | 8436 |
| (180.0, 360.0] | 8659 |
| (360.0, 720.0] | 5869 |
| (720.0, 1440.0] | 860 |
| (1440.0, inf] | 2000 |

## recipes — recipe list field parsing

| column | n_ok | n_empty | n_missing | n_not_a_list | n_malformed | mean_length | max_length |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tags | 231637 | 0 | 0 | 0 | 0 | 17.8801 | 73 |
| ingredients | 231637 | 0 | 0 | 0 | 0 | 9.0512 | 43 |
| steps | 231636 | 1 | 0 | 0 | 0 | 9.7655 | 145 |
| nutrition | 231637 | 0 | 0 | 0 | 0 | 7.0000 | 7 |

## recipes — tag vocabulary

| tag | n_recipes | whitelisted |
| --- | --- | --- |
| preparation | 230546 | False |
| time-to-make | 225326 | False |
| course | 218148 | False |
| main-ingredient | 170446 | False |
| dietary | 165091 | False |
| easy | 126062 | True |
| occasion | 114145 | False |
| cuisine | 91165 | False |
| low-in-something | 85776 | True |
| main-dish | 71786 | True |
| equipment | 70436 | False |
| 60-minutes-or-less | 69990 | False |
| number-of-servings | 58949 | False |
| meat | 56042 | True |
| 30-minutes-or-less | 55077 | False |
| vegetables | 53814 | True |
| taste-mood | 52143 | False |
| 4-hours-or-less | 49497 | False |
| north-american | 48479 | True |
| 3-steps-or-less | 44933 | False |
| 15-minutes-or-less | 43934 | False |
| low-sodium | 43349 | True |
| desserts | 43203 | True |
| low-carb | 42189 | True |
| healthy | 40340 | True |
| dinner-party | 37561 | True |
| low-cholesterol | 36743 | True |
| low-calorie | 36429 | True |
| vegetarian | 35651 | True |
| beginner-cook | 35561 | True |

_(522 further rows in the accompanying CSV.)_

## recipes — recipe derived count checks

| source_column | parsed_column | n_mismatch | pct_mismatch |
| --- | --- | --- | --- |
| n_steps | steps | 0 | 0.0000 |
| n_ingredients | ingredients | 0 | 0.0000 |

## recipes — recipes missingness

| column | dtype | n_missing | pct_missing | n_blank_string |
| --- | --- | --- | --- | --- |
| name | str | 1 | 0.0004 | 0 |
| id | Int64 | 0 | 0.0000 | 0 |
| minutes | Int64 | 0 | 0.0000 | 0 |
| contributor_id | Int64 | 0 | 0.0000 | 0 |
| submitted | str | 0 | 0.0000 | 0 |
| tags | str | 0 | 0.0000 | 0 |
| nutrition | str | 0 | 0.0000 | 0 |
| n_steps | Int64 | 0 | 0.0000 | 0 |
| steps | str | 0 | 0.0000 | 0 |
| description | str | 4979 | 2.1495 | 0 |
| ingredients | str | 0 | 0.0000 | 0 |
| n_ingredients | Int64 | 0 | 0.0000 | 0 |

## interactions — repeated pair multiplicity

_(no rows)_

## interactions — interactions by year

| year | n_interactions |
| --- | --- |
| 2000 | 108 |
| 2001 | 2904 |
| 2002 | 20922 |
| 2003 | 32961 |
| 2004 | 45950 |
| 2005 | 66643 |
| 2006 | 89794 |
| 2007 | 141158 |
| 2008 | 167295 |
| 2009 | 159445 |
| 2010 | 107409 |
| 2011 | 72147 |
| 2012 | 56410 |
| 2013 | 49488 |
| 2014 | 30503 |
| 2015 | 23374 |
| 2016 | 18147 |
| 2017 | 27062 |
| 2018 | 20647 |

## interactions — rating distribution

| rating | n_interactions |
| --- | --- |
| 0 | 60847 |
| 1 | 12818 |
| 2 | 14123 |
| 3 | 40855 |
| 4 | 187360 |
| 5 | 816364 |

## interactions — user positive history sizes

| n_distinct_positive_recipes | n_users |
| --- | --- |
| 1 | 127946 |
| 2 | 18956 |
| 3 | 8047 |
| 4 | 4610 |
| 5 | 3017 |
| 6 | 2325 |
| 7 | 1710 |
| 8 | 1308 |
| 9 | 1111 |
| 10 | 933 |
| 11 | 778 |
| 12 | 660 |
| 13 | 557 |
| 14 | 502 |
| 15 | 448 |
| 16 | 375 |
| 17 | 370 |
| 18 | 317 |
| 19 | 289 |
| 20 | 262 |
| 21 | 236 |
| 22 | 223 |
| 23 | 213 |
| 24 | 193 |
| 25 | 185 |
| 26 | 180 |
| 27 | 149 |
| 28 | 154 |
| 29 | 143 |
| 30 | 126 |

_(577 further rows in the accompanying CSV.)_

## interactions — interactions missingness

| column | dtype | n_missing | pct_missing | n_blank_string |
| --- | --- | --- | --- | --- |
| user_id | Int64 | 0 | 0.0000 | 0 |
| recipe_id | Int64 | 0 | 0.0000 | 0 |
| date | str | 0 | 0.0000 | 0 |
| rating | Int64 | 0 | 0.0000 | 0 |

## What this audit does not establish

It does not establish that the dataset is fit for any particular claim, that nutrition units are what they appear to be, or that the licence permits redistribution. Those are recorded separately and remain open until confirmed.
