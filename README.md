# negex

NegEx locates trigger terms indicating a clinical condition is negated or possible and determines which text falls within the scope of the trigger terms.

Input: a sentence with optionally indicated clinical conditions from the sentence.

Action: determine the scope of any trigger terms in the sentence.

Output: two types of output:

(1) value of indexed conditions - if you indicate the conditions whose negation status you are wondering about, NegEx will return negated or possible for those conditions within the scope of negation terms (no value is returned for the conditions if the condition is considered present);

(2) the text within the scope of a trigger term - this is a more generalized output without needing to predetermine conditions of interest.

The NegEx multilingual lexicon described in the paper below, can be downloaded here.

Wendy W. Chapman, Dieter Hilert, Sumithra Velupillai, Maria Kvist, Maria Skeppstedt, Brian E. Chapman, Michael Conway, Melissa Tharp, Danielle L. Mowery, Louise Deleger. Extending the NegEx Lexicon for Multiple Languages. Proceedings of the 14th World Congress on Medical & Health Informatics (MEDINFO 2013) 2013.
