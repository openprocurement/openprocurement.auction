function(doc){
  if ((doc.current_stage||0) == -1) {
     var mode = doc.mode||false ? doc.mode : "";
     var api_version = (doc.TENDERS_API_VERSION||false) ? doc.TENDERS_API_VERSION : null;
     var procurement_method_type = doc.procurementMethodType||null;
     var auction_type = (doc.auction_type||false) ? doc.auction_type : "default";
     emit(doc._local_seq, {
         "start": doc.stages[0].start,
         "mode": mode,
         "api_version": api_version,
         "auction_type": auction_type,
         "procurementMethodType": procurement_method_type
     });
  }
}
