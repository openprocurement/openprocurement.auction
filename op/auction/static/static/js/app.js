var app = angular.module('app', ['ui.bootstrap', 'pascalprecht.translate', 'timer']);
var db = {};


app.constant('AuctionConfig', {dbname: 'auction',
                               auction_doc_id: auction_doc_id,
                               remote_db: db_url});

app.controller('AuctionController', function($scope, $http, $log, $rootScope, AuctionConfig){
    db = $scope.db = new PouchDB(AuctionConfig.dbname);
    $scope.auction_doc = {"current_stage": null}
    PouchDB.sync(AuctionConfig.dbname, AuctionConfig.remote_db, {live: true})
    $scope.update_countdown_time = function (start_date, end_date) {
        $scope.interval = (end_date - start_date)/1000;
        $scope.$broadcast('timer-set-countdown', $scope.interval);
        $scope.$broadcast('timer-start');
    }
    $scope.sync_countdown_time_with_server = function(start) {
        $http.get('/get_corrent_server_time').success(function(data) {
            $scope.last_sync = new Date(data);;
            if ($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1]){
                var end = new Date($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1]["start"]);
            } else {
                var end = new Date($scope.auction_doc.endDate)
            }
            $scope.update_countdown_time($scope.last_sync, end)


        });
    }
    $scope.get_auction_data = function() {
        db.get(AuctionConfig.auction_doc_id, function(err, doc) {
            $log.debug("Get doc", doc);
            $rootScope.$apply(function (argument) { 
                if (($scope.auction_doc.current_stage == null)||(doc.current_stage - $scope.auction_doc.current_stage == 0)){
                    $scope.sync_countdown_time_with_server();
                } else {
                    if (doc.stages[doc.current_stage]["start"]){
                        var start = new Date(doc.stages[doc.current_stage]["start"]);
                    } else {
                        var start = new Date();
                    }
                    if (doc.stages[doc.current_stage + 1]){
                        var end = new Date(doc.stages[doc.current_stage + 1]["start"]);
                    } else {
                        var end = new Date(doc.endDate)
                    }
                    $scope.update_countdown_time(start, end)
                }         
                $scope.auction_doc = doc;
            }); 
        });
    }
    $scope.db.changes({
        live: true,
        continuous: true,
        onChange: function(change) {
            $log.debug('onChanges:info - ', change);
            if (change.id == AuctionConfig.auction_doc_id){
                $scope.get_auction_data();
            }
        }});
    $scope.get_auction_data();
    $log.debug("Finish loading");
    $scope.value = 35;
});

