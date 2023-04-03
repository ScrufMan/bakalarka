from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search, Q
from .helpers import dataset_to_indices
from entity_recognizer.post_processor import lemmatize_text

def handle_regexp(search_term):
    return [
        {
            "regexp": {
                "value": search_term[2:]
            }
        },
        {
            "regexp": {
                "lemmatized": search_term[2:]
            }
        }
    ]


def handle_exact(search_term):
    exact_term = search_term[1:-1]
    return [
        {
            "term": {
                "value.keyword": exact_term
            }
        },
        {
            "term": {
                "lemmatized.keyword": exact_term
            }
        }
    ]


def handle_normal(search_term, lemmatized_search_term):
    return [
        {
            "multi_match": {
                "query": search_term,
                "fields": ["value", "value.english"]
            }
        },
        {
            "multi_match": {
                "query": lemmatized_search_term,
                "fields": ["lemmatized", "lemmatized.english"]
            }
        },
        {
            "fuzzy": {
                "value": {
                    "value": search_term,
                    "fuzziness": "AUTO"
                }
            }
        },
        {
            "fuzzy": {
                "lemmatized": {
                    "value": lemmatized_search_term,
                    "fuzziness": "AUTO"
                }
            }
        },
        {
            "fuzzy": {
                "value.english": {
                    "value": search_term,
                    "fuzziness": "AUTO"
                }
            }
        },
        {
            "fuzzy": {
                "lemmatized.english": {
                    "value": lemmatized_search_term,
                    "fuzziness": "AUTO"
                }
            }
        }
    ]


def find_entities(es: Elasticsearch, dataset, search_terms, entity_types, page, page_size):
    lemmatized_search_terms = [lemmatize_text(term) for term in search_terms]

    indices = dataset_to_indices(es, dataset, file_indices=False)

    search = Search(using=es, index=indices)

    search_from = (page - 1) * page_size
    search = search[search_from:search_from + page_size]

    # Loop through search_terms and create a search query for each term
    search_clauses = []
    for search_term, lemmatized_search_term in zip(search_terms, lemmatized_search_terms):
        if search_term.startswith('r:'):
            search_clauses.extend(handle_regexp(search_term))
        elif search_term.startswith('"') and search_term.endswith('"'):
            search_clauses.extend(handle_exact(search_term))
        else:
            search_clauses.extend(handle_normal(search_term, lemmatized_search_term))

    search = search.query(
        "bool",
        should=search_clauses,
        filter=[
            {
                "terms": {
                    "entity_type": entity_types
                }
            }
        ],
        minimum_should_match=1
    )

    response = search.execute()

    return response


def get_all_files(es: Elasticsearch, dataset):
    indices = dataset_to_indices(es, dataset, file_indices=True)

    s = Search(using=es, index=indices)
    s = s[0:10000]
    response = s.query(Q("match_all")).execute()

    return response


def get_file(es, dataset, file_id):
    index = f"{dataset}-files"

    try:
        res = es.get(index=index, id=file_id)

        return res
    except Exception as e:
        print(f"Error retrieving document: {e}")
