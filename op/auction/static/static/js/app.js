var app = angular.module('app', ['ui.bootstrap', 'pascalprecht.translate']);
var db = {};


app.constant('AuctionConfig', {dbname: 'auction',
                               auction_doc_id: auction_doc_id,
                               remote_db: db_url});

app.controller('AuctionController', function($scope, $log, $rootScope, AuctionConfig){
    db = $scope.db = new PouchDB(AuctionConfig.dbname);
    PouchDB.sync(AuctionConfig.dbname, AuctionConfig.remote_db, {live: true})
    $scope.get_auction_data = function() {
        db.get(AuctionConfig.auction_doc_id, function(err, doc) {
            $log.debug("Get doc", doc);
            $rootScope.$apply(function (argument) {
                $scope.auction_doc = doc;
                $scope.stages = doc.stages;
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

