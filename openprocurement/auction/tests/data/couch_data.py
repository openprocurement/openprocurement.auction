# 'limit_replications_progress' in 'server_config' is undefined
l1a = [
            # 'limit_replications_func' is undefined
            ({'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1023,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),

            # 'limit_replications_func' is 'any'
            ({'server_config': {'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1023,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),

            # 'limit_replications_func' is 'all'
            ({'server_config': {'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1023,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),
        ]

# 'limit_replications_progress' in 'server_config' is 1024
l1b = [
            # 'limit_replications_func' is undefined
            ({'server_config': {'limit_replications_progress': 1024},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1023,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 1024},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 1024},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),

            # 'limit_replications_func' is 'any'
            ({'server_config': {'limit_replications_progress': 1024,
                                'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1023,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 1024,
                                'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 1024,
                                'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),

            # 'limit_replications_func' is 'all'
            ({'server_config': {'limit_replications_progress': 1024,
                                'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1023,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 1024,
                                'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 1024,
                                'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),
        ]

# 'limit_replications_progress' in 'server_config' is 512
l1c = [
            # 'limit_replications_func' is undefined
            ({'server_config': {'limit_replications_progress': 512},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 511,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 512},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 512,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 512},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 513,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),

            # 'limit_replications_func' is 'any'
            ({'server_config': {'limit_replications_progress': 512,
                                'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 511,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 512,
                                'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 512,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 512,
                                'limit_replications_func': 'any'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 513,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),

            # 'limit_replications_func' is 'all'
            ({'server_config': {'limit_replications_progress': 512,
                                'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 511,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 512,
                                'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 512,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0001": 10}'}),
            ({'server_config': {'limit_replications_progress': 512,
                                'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 513,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10}'}),
        ]

# first couch task doesn't have a type
l2a = [
            ({'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               },
                              {'replication_id': '0002',
                               'progress': 20,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }
                              ]},
             {'status_int': 200, 'body': '{"0002": 20}'}),
            ({'server_config': {'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               },
                              {'replication_id': '0002',
                               'progress': 20,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0002": 20}'}),
        ]

# first couch task has type 'smth'
l2b = [
            ({'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'smth',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               },
                              {'replication_id': '0002',
                               'progress': 20,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0002": 20}'}),

            ({'server_config': {'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'smth',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               },
                              {'replication_id': '0002',
                               'progress': 20,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 200, 'body': '{"0002": 20}'}),
        ]

# check difference between 'any', and 'all' for 'limit_replications_func' key
l3 = [
            ({'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               },
                              {'replication_id': '0002',
                               'progress': 20,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0,
                               'xxx': 'xxx'
                               }
                              ]},
             {'status_int': 200, 'body': '{"0001": 10, "0002": 20}'}),
            ({'server_config': {'limit_replications_func': 'all'},
              'couch_tasks': [{'replication_id': '0001',
                               'progress': 10,
                               'type': 'replication',
                               'source_seq': 1024,
                               'checkpointed_source_seq': 0
                               },
                              {'replication_id': '0002',
                               'progress': 20,
                               'type': 'replication',
                               'source_seq': 1025,
                               'checkpointed_source_seq': 0
                               }]},
             {'status_int': 503, 'body': '{"0001": 10, "0002": 20}'}),
]
