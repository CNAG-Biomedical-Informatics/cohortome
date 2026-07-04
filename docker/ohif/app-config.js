window.config = {
  routerBasename: "/",
  showStudyList: true,
  maxNumberOfWebWorkers: 3,
  dataSources: [
    {
      namespace: "@ohif/extension-default.dataSourcesModule.dicomweb",
      sourceName: "orthanc",
      configuration: {
        friendlyName: "BRN Orthanc",
        name: "orthanc",
        qidoRoot: "http://127.0.0.1:8042/dicom-web",
        wadoRoot: "http://127.0.0.1:8042/dicom-web",
        wadoUriRoot: "http://127.0.0.1:8042/wado",
        qidoSupportsIncludeField: true,
        supportsReject: false,
        imageRendering: "wadors",
        thumbnailRendering: "wadors",
        enableStudyLazyLoad: true,
        supportsFuzzyMatching: false,
        supportsWildcard: true,
        staticWado: false,
        singlepart: "bulkdata,video"
      }
    }
  ],
  defaultDataSourceName: "orthanc"
};
