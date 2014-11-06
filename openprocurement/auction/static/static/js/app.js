var app = angular.module('app', ['ui.bootstrap', 'pascalprecht.translate', 'timer']);
var db = {};
var bidder_id = "0"

app.constant('AuctionConfig', {
    dbname: 'auction',
    auction_doc_id: auction_doc_id,
    remote_db: db_url
});

app.controller('AuctionController', function($scope, $http, $log, $rootScope, AuctionConfig) {
    db = $scope.db = new PouchDB(AuctionConfig.dbname);
    $scope.auction_doc = {
        "current_stage": null,

    }
    PouchDB.sync(AuctionConfig.dbname, AuctionConfig.remote_db, {
        live: true
    })
    $scope.update_countdown_time = function(start_date, end_date) {
        $scope.interval = (end_date - start_date) / 1000;
        if ($scope.interval > 0) {
            $scope.$broadcast('timer-set-countdown', $scope.interval);
            $scope.$broadcast('timer-start');
        };
    }
    $scope.sync_countdown_time_with_server = function(start) {
        $http.get('/get_corrent_server_time').success(function(data) {
            $scope.last_sync = new Date(data);;
            if (($scope.auction_doc) && ($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1])) {
                var end = new Date($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1]["start"]);
            } else if ($scope.auction_doc) {
                var end = new Date($scope.auction_doc.endDate);
            } else {
                var end = new Date();
            }
            $scope.update_countdown_time($scope.last_sync, end)
        });
    }
    $scope.post_bid = function() {
        if ($scope.BidsForm.$valid) {
            $http.post('/postbid', {
                'bid': $scope.BidsForm.bid,
                'bidder_id': bidder_id || "0"
            }).success(function(data) {
                if (data.status == 'failed') {
                    $log.error('Errors while biding:', data.errors);
                } else {
                    $log.info('Success bid:', data.data);
                }
            });
        }
    };
    $scope.get_auction_data = function() {
        db.get(AuctionConfig.auction_doc_id, function(err, doc) {
            $log.debug("Get doc", doc);
            $rootScope.$apply(function(argument) {
                $scope.auction_doc = doc;
            });
        });
    }
    $scope.db.changes({
        live: true,
        continuous: true,
        include_docs: true,
        onChange: function(change) {
            $log.debug('onChanges:info - ', change);
            if (change.id == AuctionConfig.auction_doc_id) {
                $rootScope.$apply(function(argument) {
                    if (($scope.auction_doc.current_stage == null) || (change.doc.current_stage - $scope.auction_doc.current_stage == 0)) {
                        $scope.sync_countdown_time_with_server();
                    } else {
                        if (change.doc.stages[change.doc.current_stage]["start"]) {
                            var start = new Date(change.doc.stages[change.doc.current_stage]["start"]);
                        } else {
                            var start = new Date();
                        }
                        if (change.doc.stages[change.doc.current_stage + 1]) {
                            var end = new Date(change.doc.stages[change.doc.current_stage + 1]["start"]);
                        } else {
                            var end = new Date(change.doc.endDate)
                        }
                        $scope.update_countdown_time(start, end)
                    }
                    $scope.auction_doc = change.doc;
                });
            }
        }
    });
    // $scope.get_auction_data();
    $log.debug("Finish loading");
});